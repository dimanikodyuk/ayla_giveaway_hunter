"""Read-only collection. Run separately: python -m app.collector"""
import os,asyncio,logging,hashlib,re,sqlite3
from difflib import SequenceMatcher
from datetime import timedelta
from datetime import datetime,timezone
from urllib.parse import urlparse
from pathlib import Path
import httpx,feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv
try:
    from .main import ROOT,conn,init_db,now,GiveawayIn,insert_giveaway,queue_new_giveaway
    from .engine import analyze
except ImportError:
    from bootstrap import ROOT as _ROOT
    import sys
    sys.path.insert(0, str(_ROOT))
    from app.main import ROOT,conn,init_db,now,GiveawayIn,insert_giveaway,queue_new_giveaway
    from app.engine import analyze
load_dotenv(ROOT/'.env');log=logging.getLogger('collector')
from .dedup import find_linked_giveaway
from .giveaway_metadata import extract as extract_giveaway_metadata, is_ended, metadata_title, serialize

def historical_reason(info, published_at, native=False, now_utc=None):
    """Return reason if participation is certainly over or an undated post is stale."""
    current=now_utc or datetime.now(timezone.utc)
    def parsed(value):
        if not value:return None
        try:
            d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
            return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
        except (TypeError,ValueError):return None
    dates=info.get('dates') or []
    entry=[parsed(x.get('at')) for x in dates if x.get('kind')=='entry_deadline']
    winner=[parsed(x.get('at')) for x in dates if x.get('kind')=='winner_selection']
    dated=[x for x in entry+winner if x is not None]
    if dated and any(x <= current for x in dated):
        return 'Завершена дата участі або вибору переможців'
    published=parsed(published_at)
    # Do not guess whether an undated, month-old post is still open.
    if published and published < current-timedelta(days=7) and not dated:
        return 'Старе повідомлення без підтвердженої актуальної дати'
    return None

def record(sid,external_id,text,url,published_at=None,native=False,metadata=None):
    info=analyze(text,published_at,native=native)
    with conn() as c:
        try:
            cur=c.execute('INSERT INTO raw_items(source_id,external_id,raw_text,fetched_at) VALUES(?,?,?,?)',(sid,external_id,(text or '')[:100000],now()))
        except sqlite3.IntegrityError:
            # Backfill metadata for already-scanned native posts without changing review or participation.
            if native and metadata:
                c.execute('''UPDATE giveaways SET telegram_metadata=?,
                    deadline_at=COALESCE(deadline_at,?)
                    WHERE source_url=? AND native_giveaway=1''',
                    (serialize(metadata), metadata.get('until_date'), url))
            return False
        from app.main import collect_channel_mentions
        collect_channel_mentions(c,cur.lastrowid,text)
        if native and is_ended(metadata): return False
        if not info['candidate']:return False
        expired=historical_reason(info,published_at,native=native)
        if expired:
            log.debug('Skipping historical candidate %s: %s',url,expired)
            return False
        title=(metadata_title(metadata) if native and metadata else next((x.strip() for x in (text or '').splitlines() if x.strip()),'Telegram Giveaway'))[:190]
        if len(title)<3:title='Розіграш: '+title
        entry=next((d['at'] for d in info['dates'] if d['kind']=='entry_deadline'),None)
        winner=next((d['at'] for d in info['dates'] if d['kind']=='winner_selection'),None)
        announcement=next((d['at'] for d in info['dates'] if d['kind']=='announcement'),None)
        if native and metadata and metadata.get('until_date'):entry=metadata['until_date']
        try:
            gid=insert_giveaway(c,GiveawayIn(title=title,source_url=url,prize='',tasks=info['tasks']),info['review_status'],info['risk_score'])
            c.execute('UPDATE giveaways SET raw_item_id=?,original_text=?,classification=?,confidence=?,classification_reason=?,published_at=?,deadline_at=?,winner_at=?,announcement_at=?,native_giveaway=?,entry_cost=?,telegram_metadata=? WHERE id=?',
                      (cur.lastrowid,text,info['category'],info['confidence'],info['reason'],published_at,entry,winner,announcement,int(native),info['entry_cost'],serialize(metadata),gid))
            linked=find_linked_giveaway(c,sid,text,published_at,native,exclude_id=gid)
            if linked:
                parent,reason=linked
                c.execute('UPDATE giveaways SET linked_giveaway_id=?,dedup_reason=? WHERE id=?',(parent,reason,gid))
            if not linked:queue_new_giveaway(c,gid,title,url)
        except sqlite3.IntegrityError:pass
        return True

async def website(source):
    # RSS/Atom feeds only: no arbitrary HTML crawling or user-controlled network fetching.
    async with httpx.AsyncClient(timeout=15,follow_redirects=False,headers={'User-Agent':'AylaGiveawayHunter/1.0'}) as client:
        u=urlparse(source['url'])
        # DNS rebinding/SSRF: no arbitrary internal URL requests; check resolved IPs.
        import socket,ipaddress
        ips=await asyncio.to_thread(socket.getaddrinfo,u.hostname,None)
        if any(not ipaddress.ip_address(item[4][0]).is_global for item in ips):raise ValueError('Source resolves to non-public IP')
        r=await client.get(source['url']);r.raise_for_status()
        if len(r.content)>2_000_000:raise ValueError('Feed too large')
        feed=feedparser.parse(r.content)
        if not feed.entries:raise ValueError('No RSS/Atom entries (HTML crawling is not supported in v1.0)')
        n=0
        for entry in feed.entries[:50]:
            link=entry.get('link','')
            if not link.startswith('https://'):continue
            text=BeautifulSoup((entry.get('title','')+'\n'+entry.get('summary','')),'html.parser').get_text(' ',strip=True)
            eid=str(entry.get('id') or link)
            n+=bool(record(source['id'],eid,text,link))
        return n
async def telegram_batch(sources):
    if os.getenv('TELEGRAM_COLLECTOR_MODE','user').lower() == 'off':
        return {s['id']:(0,'Telegram user collector disabled by configuration') for s in sources}
    api_id=os.getenv('TG_API_ID');api_hash=os.getenv('TG_API_HASH')
    if not api_id or not api_hash:raise RuntimeError('TG_API_ID and TG_API_HASH are not configured')
    from telethon import TelegramClient
    session=str(ROOT/'data'/'telegram_user')
    # Requires initial interactive login: python -m app.telegram_login
    async with TelegramClient(session,int(api_id),api_hash) as client:
        if not await client.is_user_authorized():raise RuntimeError('Run QR user login first')
        me=await client.get_me()
        if me is None or me.bot:raise RuntimeError('Collector requires a USER session, not a bot session')
        result={}
        for s in sources:
            count=0
            try:
                username=urlparse(s['url']).path.strip('/').split('/')[0]
                if not re.fullmatch(r'[A-Za-z0-9_]{5,32}',username):raise ValueError('Only public channel usernames supported')
                async for m in client.iter_messages(username,limit=120,reverse=True):
                    from telethon.tl import types
                    native=isinstance(getattr(m,'action',None),(types.MessageActionGiveawayLaunch,types.MessageActionGiveawayResults)) or type(getattr(m,'media',None)).__name__=='MessageMediaGiveaway'
                    if not m.message and not native:continue
                    metadata=extract_giveaway_metadata(m) if native else None
                    if native and not m.message:
                        m.message=metadata_title(metadata)
                    link=f'https://t.me/{username}/{m.id}'
                    count+=bool(record(s['id'],str(m.id),m.message,link,m.date.isoformat() if m.date else None,native,metadata))
                result[s['id']]=(count,None)
            except Exception as e:result[s['id']]=(0,str(e)[:300])
        return result
def save_run(sid,start,count,error):
    with conn() as c:
        c.execute('INSERT INTO scan_runs(source_id,started_at,finished_at,status,items_found,error) VALUES(?,?,?,?,?,?)',(sid,start,now(),'ERROR' if error else 'OK',count,error))
        if not error:c.execute('UPDATE sources SET last_scan_at=? WHERE id=?',(now(),sid))
async def scan_once():
    with conn() as c:sources=[dict(r) for r in c.execute('SELECT * FROM sources WHERE enabled=1')]
    sites=[s for s in sources if s['type']=='website'];tgs=[s for s in sources if s['type']=='telegram']
    for s in sites:
        start=now()
        try:count=await website(s);error=None
        except Exception as e:count=0;error=str(e)[:300];log.warning('Website %s: %s',s['title'],error)
        save_run(s['id'],start,count,error)
    if tgs and os.getenv('TELEGRAM_COLLECTOR_MODE','user').lower() != 'off':
        start=now()
        try:results=await telegram_batch(tgs)
        except Exception as e:results={s['id']:(0,str(e)[:300]) for s in tgs}
        for s in tgs:
            count,error=results[s['id']];save_run(s['id'],start,count,error)
async def run():
    init_db()
    while True:
        try:await scan_once()
        except Exception:log.exception('Scan cycle failed')
        await asyncio.sleep(max(300,int(os.getenv('SCAN_INTERVAL_SECONDS','900'))))
if __name__=='__main__':
    logging.basicConfig(level=logging.INFO);asyncio.run(run())

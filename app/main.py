# Direct PyCharm Run: start the canonical package module instead of loading
# this file twice as __main__ and app.main (which causes circular imports).
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    from pathlib import Path as _Path
    _root = _Path(__file__).resolve().parents[1]
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_root / ".env")
    import uvicorn as _uvicorn
    _uvicorn.run("app.main:app", host=_os.getenv("HOST", "0.0.0.0"),
                 port=int(_os.getenv("PORT", "8093")))
    _sys.exit(0)

import os,sqlite3,secrets,ipaddress,asyncio,json,logging
from contextlib import contextmanager,asynccontextmanager
from pathlib import Path
from datetime import datetime,timezone
from typing import Optional
from urllib.parse import urlparse
from fastapi import FastAPI,HTTPException,Request,Depends,Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,field_validator
from dotenv import load_dotenv
if __package__ in (None, ''):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine import normalize_url,analyze
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
DB=Path(os.getenv('GIVEAWAY_DB',str(ROOT/'data'/'giveaways.sqlite3')))
AUTH_MODE=os.getenv('AUTH_MODE','local').lower(); TOKEN=os.getenv('GIVEAWAY_TOKEN','')
log=logging.getLogger(__name__)
def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def conn():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA synchronous=FULL');c.execute('PRAGMA busy_timeout=20000')
    try:
        yield c;c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()
def init_db():
    with conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,type TEXT NOT NULL CHECK(type IN ('telegram','website')),title TEXT NOT NULL,url TEXT NOT NULL UNIQUE,enabled INTEGER NOT NULL DEFAULT 1,last_scan_at TEXT);
        CREATE TABLE IF NOT EXISTS raw_items(id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL REFERENCES sources(id),external_id TEXT NOT NULL,raw_text TEXT NOT NULL,fetched_at TEXT NOT NULL,UNIQUE(source_id,external_id));
        CREATE TABLE IF NOT EXISTS giveaways(id INTEGER PRIMARY KEY,title TEXT NOT NULL,prize TEXT NOT NULL DEFAULT '',organizer TEXT NOT NULL DEFAULT '',source_url TEXT NOT NULL UNIQUE,deadline_at TEXT,country_scope TEXT NOT NULL DEFAULT 'unknown',review_status TEXT NOT NULL DEFAULT 'REVIEW' CHECK(review_status IN ('REVIEW','APPROVED','REJECTED')),risk_score INTEGER NOT NULL DEFAULT 50 CHECK(risk_score BETWEEN 0 AND 100),created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,description TEXT NOT NULL,action_url TEXT,sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS participations(id INTEGER PRIMARY KEY,giveaway_id INTEGER NOT NULL UNIQUE REFERENCES giveaways(id) ON DELETE CASCADE,status TEXT NOT NULL DEFAULT 'NEW' CHECK(status IN ('NEW','IN_PROGRESS','ENTERED','AWAITING_RESULT','WON','LOST','UNKNOWN','SKIPPED','DISQUALIFIED','EXPIRED')),notes TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS task_progress(task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,completed INTEGER NOT NULL DEFAULT 0,completed_at TEXT);
        CREATE TABLE IF NOT EXISTS scan_runs(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES sources(id),started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,items_found INTEGER NOT NULL DEFAULT 0,error TEXT);
        CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_giveaways_deadline ON giveaways(deadline_at);
        CREATE INDEX IF NOT EXISTS idx_participations_status ON participations(status);
        CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_items(source_id);''')
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(1,?)',(now(),))
        # Idempotent additive migration, preserving existing records.
        cols={r['name'] for r in c.execute('PRAGMA table_info(giveaways)')}
        for name,typ in [('raw_item_id','INTEGER'),('original_text','TEXT'),('classification','TEXT'),('confidence','INTEGER'),('classification_reason','TEXT'),('published_at','TEXT'),('winner_at','TEXT'),('announcement_at','TEXT'),('native_giveaway','INTEGER DEFAULT 0')]:
            if name not in cols:c.execute(f'ALTER TABLE giveaways ADD COLUMN {name} {typ}')
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(2,?)',(now(),))
        c.execute("""CREATE TABLE IF NOT EXISTS notification_outbox (
            id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
            giveaway_id INTEGER REFERENCES giveaways(id) ON DELETE SET NULL,
            chat_id INTEGER NOT NULL, text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT, created_at TEXT NOT NULL, sent_at TEXT, last_error TEXT)
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_outbox_status ON notification_outbox(status,next_attempt_at)")
        c.execute("CREATE TABLE IF NOT EXISTS review_audit(id INTEGER PRIMARY KEY,giveaway_id INTEGER NOT NULL,action TEXT NOT NULL,old_value TEXT,new_value TEXT,created_at TEXT NOT NULL)")
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(3,?)',(now(),))
        cols={r['name'] for r in c.execute('PRAGMA table_info(giveaways)')}
        for name,typ in [('entry_cost',"TEXT DEFAULT 'unknown'"),('linked_giveaway_id','INTEGER'),('dedup_reason','TEXT'),('telegram_metadata','TEXT')]:
            if name not in cols:c.execute(f'ALTER TABLE giveaways ADD COLUMN {name} {typ}')
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(4,?)',(now(),))
        c.execute('''CREATE TABLE IF NOT EXISTS participation_audit (
            id INTEGER PRIMARY KEY, giveaway_id INTEGER NOT NULL,
            old_status TEXT, new_status TEXT NOT NULL,
            actor TEXT NOT NULL, changed_at TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_participation_audit_gid ON participation_audit(giveaway_id,id)')
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(5,?)',(now(),))
@asynccontextmanager
async def lifespan(app):
    init_db();yield
app=FastAPI(title='Ayla Giveaway Hunter',version='3.1.0',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=ROOT/'app'/'static'),name='static')
def auth(request:Request,x_admin_token:Optional[str]=Header(default=None)):
    if AUTH_MODE=='local':
        host=request.client.host if request.client else ''
        try: local=ipaddress.ip_address(host).is_loopback
        except ValueError: local=False
        if local:return
    if TOKEN and x_admin_token and secrets.compare_digest(x_admin_token,TOKEN):return
    raise HTTPException(401,'Authorization required. Use loopback local mode or X-Admin-Token')
class GiveawayIn(BaseModel):
    title:str=Field(min_length=3,max_length=200)
    prize:str=Field(default='',max_length=200)
    organizer:str=Field(default='',max_length=200)
    source_url:str=Field(max_length=2000)
    deadline_at:Optional[datetime]=None
    country_scope:str='unknown'
    tasks:list[str]=Field(default_factory=list,max_length=20)
    @field_validator('source_url',mode='before')
    @classmethod
    def url(cls,v):return normalize_url(v)
class SourceIn(BaseModel):
    type:str=Field(pattern='^(telegram|website)$')
    title:str=Field(min_length=2,max_length=150)
    url:str=Field(max_length=2000)
    @field_validator('url',mode='before')
    @classmethod
    def url_check(cls,v):
        u=normalize_url(v)
        if cls is SourceIn:pass
        return u
class StatusIn(BaseModel):status:str
class DateEdit(BaseModel):
    deadline_at:Optional[datetime]=None
    winner_at:Optional[datetime]=None
    @field_validator('deadline_at','winner_at')
    @classmethod
    def must_be_timezone_aware(cls,v):
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError('Specify timezone offset, e.g. +02:00 or Z')
        return v
class ProgressIn(BaseModel):completed:bool
@app.get('/')
def index():return FileResponse(ROOT/'app'/'static'/'index.html')
@app.get('/api/health')
def health():return {'status':'ok','version':'3.1.0'}
@app.get('/api/config')
def config(request:Request):
    try:local=ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError,AttributeError):local=False
    return {'auth_required':not(AUTH_MODE=='local' and local),'mode':AUTH_MODE}
@app.get('/api/giveaways',dependencies=[Depends(auth)])
def giveaways():
    with conn() as c:
        rows=c.execute('SELECT g.*,p.status AS participation_status FROM giveaways g LEFT JOIN participations p ON p.giveaway_id=g.id ORDER BY g.id DESC').fetchall();result=[]
        for row in rows:
            d=dict(row);d['tasks']=[dict(x) for x in c.execute('SELECT t.*,COALESCE(tp.completed,0) AS completed FROM tasks t LEFT JOIN task_progress tp ON tp.task_id=t.id WHERE t.giveaway_id=? ORDER BY t.sort_order,t.id',(row['id'],))];result.append(d)
        return result
def insert_giveaway(c,data,review='REVIEW',risk=50):
    cur=c.execute('INSERT INTO giveaways(title,prize,organizer,source_url,deadline_at,country_scope,review_status,risk_score,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(data.title,data.prize,data.organizer,data.source_url,data.deadline_at.isoformat() if data.deadline_at else None,data.country_scope,review,risk,now()))
    gid=cur.lastrowid
    for i,t in enumerate(data.tasks):c.execute('INSERT INTO tasks(giveaway_id,description,sort_order) VALUES(?,?,?)',(gid,t,i))
    c.execute('INSERT INTO participations(giveaway_id,updated_at) VALUES(?,?)',(gid,now()))
    return gid
def queue_new_giveaway(c,gid:int,title:str,url:str):
    """Candidate notifications are intentionally silent. Daily digest is user-controlled."""
    return None

@app.get('/api/giveaways/{gid}/detail',dependencies=[Depends(auth)])
def giveaway_detail(gid:int):
    with conn() as c:
        row=c.execute('SELECT g.*,s.title AS source_title,r.raw_text AS archived_text FROM giveaways g LEFT JOIN raw_items r ON r.id=g.raw_item_id LEFT JOIN sources s ON s.id=r.source_id WHERE g.id=?',(gid,)).fetchone()
        if not row:raise HTTPException(404,'Giveaway not found')
        d=dict(row);d['full_text']=d['original_text'] or d['archived_text'] or ''
        # Legacy records may lack raw_item_id. Match the original Telegram post by
        # source URL and message ID against archived raw_items, without guessing text.
        if not d['full_text'] and d['source_url']:
            from urllib.parse import urlparse
            import re
            match=re.fullmatch(r'/([A-Za-z0-9_]{5,32})/(\d+)',urlparse(d['source_url']).path)
            if match:
                username,msg_id=match.groups()
                legacy=c.execute("""SELECT r.raw_text FROM raw_items r
                    JOIN sources s ON s.id=r.source_id
                    WHERE r.external_id=? AND (lower(s.url)=? OR lower(s.url)=?)
                    ORDER BY r.id DESC LIMIT 1""",(msg_id,'https://t.me/'+username.lower(),'https://telegram.me/'+username.lower())).fetchone()
                if legacy:d['full_text']=legacy['raw_text']
        d['text_available']=bool(d['full_text'])
        d['tasks']=[dict(x) for x in c.execute('SELECT t.*,COALESCE(p.completed,0) AS completed FROM tasks t LEFT JOIN task_progress p ON p.task_id=t.id WHERE t.giveaway_id=? ORDER BY t.sort_order,t.id',(gid,))]
        return d

@app.post('/api/reclassify',dependencies=[Depends(auth)])
def reclassify():
    """Re-evaluate only machine-classified records; preserve manually approved decisions."""
    counts={'checked':0,'rejected':0,'review':0,'giveaways':0,'unchanged':0}
    with conn() as c:
        rows=c.execute("""SELECT g.id,g.original_text,g.classification,g.published_at,g.native_giveaway,
            g.review_status,r.raw_text AS archived_text
            FROM giveaways g LEFT JOIN raw_items r ON r.id=g.raw_item_id
            WHERE g.classification IS NOT NULL AND g.review_status = 'REVIEW'""").fetchall()
        for row in rows:
            text=row['original_text'] or row['archived_text'] or ''
            if not text:
                counts['unchanged']+=1
                continue
            result=analyze(text,row['published_at'],bool(row['native_giveaway']))
            counts['checked']+=1
            category=result['category']
            review_status='REJECTED' if not result['candidate'] else 'REVIEW'
            dates=result['dates']
            entry=next((d['at'] for d in dates if d['kind']=='entry_deadline'),None)
            winner=next((d['at'] for d in dates if d['kind']=='winner_selection'),None)
            announcement=next((d['at'] for d in dates if d['kind']=='announcement'),None)
            c.execute("""UPDATE giveaways SET classification=?,confidence=?,classification_reason=?,
                review_status=?,deadline_at=?,winner_at=?,announcement_at=? WHERE id=?""",
                (category,result['confidence'],result['reason'],review_status,entry,winner,announcement,row['id']))
            if review_status=='REJECTED':counts['rejected']+=1
            else:counts['giveaways']+=1
    return counts

@app.get('/api/review-queue' ,dependencies=[Depends(auth)])
def review_queue():
    with conn() as c:
        return [dict(r) for r in c.execute('SELECT r.id,r.raw_text,r.external_id,s.title AS source_title FROM raw_items r JOIN sources s ON s.id=r.source_id LEFT JOIN giveaways g ON g.raw_item_id=r.id WHERE g.id IS NULL ORDER BY r.id DESC LIMIT 100')]

@app.post('/api/giveaways',status_code=201,dependencies=[Depends(auth)])
def create(data:GiveawayIn):
    with conn() as c:
        try:return {'id':insert_giveaway(c,data)}
        except sqlite3.IntegrityError:raise HTTPException(409,'Giveaway URL already exists')
@app.patch('/api/tasks/{task_id}/progress',dependencies=[Depends(auth)])
def progress(task_id:int,data:ProgressIn):
    with conn() as c:
        if not c.execute('SELECT 1 FROM tasks WHERE id=?',(task_id,)).fetchone():raise HTTPException(404,'Task not found')
        c.execute('INSERT INTO task_progress(task_id,completed,completed_at) VALUES(?,?,?) ON CONFLICT(task_id) DO UPDATE SET completed=excluded.completed,completed_at=excluded.completed_at',(task_id,int(data.completed),now() if data.completed else None))
        return {'ok':True}
ALLOWED={'NEW','IN_PROGRESS','ENTERED','AWAITING_RESULT','WON','LOST','UNKNOWN','SKIPPED','DISQUALIFIED','EXPIRED'}
def set_participation_status(c,gid:int,new_status:str,actor:str='manual'):
    if new_status not in ALLOWED:raise ValueError('Invalid status')
    old=c.execute('SELECT status FROM participations WHERE giveaway_id=?',(gid,)).fetchone()
    if not old:return False
    if old['status']!=new_status:
        stamp=now()
        c.execute('UPDATE participations SET status=?,updated_at=? WHERE giveaway_id=?',(new_status,stamp,gid))
        c.execute('INSERT INTO participation_audit(giveaway_id,old_status,new_status,actor,changed_at) VALUES(?,?,?,?,?)',
                  (gid,old['status'],new_status,actor,stamp))
        if new_status in ('WON','LOST'):
            c.execute("UPDATE notification_outbox SET status='CANCELLED' WHERE giveaway_id=? AND status='PENDING' AND event_key LIKE 'result:%'",(gid,))
    return True

@app.patch('/api/giveaways/{gid}/status',dependencies=[Depends(auth)])
def status(gid:int,data:StatusIn):
    if data.status not in ALLOWED:raise HTTPException(422,'Invalid status')
    with conn() as c:
        if not set_participation_status(c,gid,data.status,'web'):
            raise HTTPException(404,'Giveaway not found')
        return {'ok':True}

@app.get('/api/giveaways/{gid}/participation-history',dependencies=[Depends(auth)])
def participation_history(gid:int):
    with conn() as c:
        if not c.execute('SELECT 1 FROM giveaways WHERE id=?',(gid,)).fetchone():
            raise HTTPException(404,'Giveaway not found')
        return [dict(r) for r in c.execute('SELECT old_status,new_status,actor,changed_at FROM participation_audit WHERE giveaway_id=? ORDER BY id DESC',(gid,))]
@app.patch('/api/giveaways/{gid}/review',dependencies=[Depends(auth)])
def review(gid:int,data:dict):
    st=data.get('status')
    if st not in ('REVIEW','APPROVED','REJECTED'):raise HTTPException(422,'Invalid review status')
    with conn() as c:
        old=c.execute('SELECT review_status FROM giveaways WHERE id=?',(gid,)).fetchone()
        if not old:raise HTTPException(404,'Not found')
        c.execute('UPDATE giveaways SET review_status=? WHERE id=?',(st,gid))
        c.execute('INSERT INTO review_audit(giveaway_id,action,old_value,new_value,created_at) VALUES(?,?,?,?,?)',(gid,'REVIEW',old['review_status'],st,now()))
    return {'ok':True}
@app.patch('/api/giveaways/{gid}/dates',dependencies=[Depends(auth)])
def edit_dates(gid:int,data:DateEdit):
    with conn() as c:
        old=c.execute('SELECT deadline_at,winner_at FROM giveaways WHERE id=?',(gid,)).fetchone()
        if not old:raise HTTPException(404,'Розіграш не знайдено')
        deadline=data.deadline_at.isoformat() if data.deadline_at else None
        winner=data.winner_at.isoformat() if data.winner_at else None
        c.execute('UPDATE giveaways SET deadline_at=?,winner_at=? WHERE id=?',(deadline,winner,gid))
        c.execute('INSERT INTO review_audit(giveaway_id,action,old_value,new_value,created_at) VALUES(?,?,?,?,?)',
                  (gid,'EDIT_DATES',json.dumps(dict(old)),json.dumps({'deadline_at':deadline,'winner_at':winner}),now()))
    return {'ok':True,'deadline_at':deadline,'winner_at':winner}

@app.delete('/api/giveaways/{gid}',dependencies=[Depends(auth)])
def delete_giveaway(gid:int):
    # Soft deletion is intentional: preserve the source URL to prevent re-import.
    with conn() as c:
        old=c.execute('SELECT review_status FROM giveaways WHERE id=?',(gid,)).fetchone()
        if not old:raise HTTPException(404,'Розіграш не знайдено')
        c.execute("UPDATE giveaways SET review_status='REJECTED' WHERE id=?",(gid,))
        c.execute('INSERT INTO review_audit(giveaway_id,action,old_value,new_value,created_at) VALUES(?,?,?,?,?)',
                  (gid,'REJECT',old['review_status'],'REJECTED',now()))
    return {'ok':True,'deleted':False,'review_status':'REJECTED'}

@app.get('/api/sources',dependencies=[Depends(auth)])
def sources():
    with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM sources ORDER BY id DESC')]
@app.post('/api/sources',status_code=201,dependencies=[Depends(auth)])
def add_source(data:SourceIn):
    if data.type=='telegram' and urlparse(data.url).hostname not in ('t.me','telegram.me'):raise HTTPException(422,'Telegram source must be t.me link')
    with conn() as c:
        try:return {'id':c.execute('INSERT INTO sources(type,title,url) VALUES(?,?,?)',(data.type,data.title,data.url)).lastrowid}
        except sqlite3.IntegrityError:raise HTTPException(409,'Source already exists')
@app.patch('/api/sources/{sid}',dependencies=[Depends(auth)])
def toggle_source(sid:int,data:dict):
    if not isinstance(data.get('enabled'),bool):raise HTTPException(422,'enabled must be boolean')
    with conn() as c:
        if not c.execute('UPDATE sources SET enabled=? WHERE id=?',(int(data['enabled']),sid)).rowcount:raise HTTPException(404,'Source not found')
    return {'ok':True}
# Curated discovery candidates. Adding sources is explicit and idempotent.
CURATED_CHANNELS=(
    ('ROZETKA','rrozetka'),('hotline.finance','hotlinefinance'),
    ('MOYO Gaming','moyo_gaming'),('КіберКарась','kiber_karas'),
)
@app.get('/api/source-candidates',dependencies=[Depends(auth)])
def source_candidates():
    with conn() as c:
        existing={r['url'].rstrip('/').lower() for r in c.execute('SELECT url FROM sources')}
    return [{'title':title,'username':username,'url':'https://t.me/'+username,
             'added':('https://t.me/'+username).lower() in existing} for title,username in CURATED_CHANNELS]

@app.post('/api/source-candidates/add',dependencies=[Depends(auth)])
def add_candidates():
    added=[];existing=[]
    with conn() as c:
        for title,username in CURATED_CHANNELS:
            url='https://t.me/'+username
            row=c.execute("SELECT id FROM sources WHERE lower(rtrim(url,'/'))=?",(url.lower(),)).fetchone()
            if row:existing.append(username);continue
            c.execute('INSERT INTO sources(type,title,url,enabled) VALUES(?,?,?,1)',('telegram',title,url))
            added.append(username)
    return {'added':added,'already_present':existing}

@app.get('/api/source-quality',dependencies=[Depends(auth)])
def source_quality():
    with conn() as c:
        rows=c.execute('''SELECT s.id,s.title,s.url,s.enabled,
            COUNT(DISTINCT r.id) AS messages,
            COUNT(DISTINCT g.id) AS candidates,
            COUNT(DISTINCT CASE WHEN g.review_status='APPROVED' THEN g.id END) AS approved,
            COUNT(DISTINCT CASE WHEN g.review_status='REJECTED' THEN g.id END) AS rejected,
            COUNT(DISTINCT CASE WHEN g.entry_cost='free' THEN g.id END) AS free,
            COUNT(DISTINCT CASE WHEN g.entry_cost='paid' THEN g.id END) AS paid,
            COUNT(DISTINCT CASE WHEN g.linked_giveaway_id IS NOT NULL THEN g.id END) AS duplicates
            FROM sources s LEFT JOIN raw_items r ON r.source_id=s.id
            LEFT JOIN giveaways g ON g.raw_item_id=r.id
            GROUP BY s.id ORDER BY s.id''').fetchall()
        result=[]
        for row in rows:
            d=dict(row)
            scan=c.execute('SELECT status,items_found,error,finished_at FROM scan_runs WHERE source_id=? ORDER BY id DESC LIMIT 1',(d['id'],)).fetchone()
            d['last_scan']=dict(scan) if scan else None
            d['approval_rate_pct']=round(100*d['approved']/d['candidates'],1) if d['candidates'] else None
            result.append(d)
        return result

@app.post('/api/sources/scan-test',dependencies=[Depends(auth)])
async def test_scan_sources():
    # Actual Telegram access only via user's existing local Telethon session.
    from app.collector import telegram_batch,save_run
    with conn() as c:
        sources=[dict(r) for r in c.execute("SELECT * FROM sources WHERE type='telegram' AND enabled=1 AND lower(rtrim(url,'/')) IN (?,?,?,?)",tuple('https://t.me/'+u for _,u in CURATED_CHANNELS))]
    if not sources:raise HTTPException(400,'Спочатку додайте джерела')
    if os.getenv('TELEGRAM_COLLECTOR_MODE','user').lower()=='off':
        raise HTTPException(409,'Telegram Collector вимкнено; тестове сканування недоступне')
    started=now()
    try:results=await telegram_batch(sources)
    except Exception as exc:results={r['id']:(0,str(exc)[:300]) for r in sources}
    output=[]
    for source in sources:
        count,error=results[source['id']]
        save_run(source['id'],started,count,error)
        output.append({'source':source['title'],'new_candidates':count,'status':'ERROR' if error else 'OK','error':error})
    return {'results':output,'note':'Кількість нових кандидатів, а не всіх повідомлень. Повторне сканування не дублює raw_items.'}

@app.get('/api/diagnostics',dependencies=[Depends(auth)])
def diagnostics():
    with conn() as c:
        return {'database':str(DB),'giveaways':c.execute('SELECT COUNT(*) FROM giveaways').fetchone()[0],'raw_items':c.execute('SELECT COUNT(*) FROM raw_items').fetchone()[0],'sources':c.execute('SELECT COUNT(*) FROM sources').fetchone()[0],'scans':[dict(r) for r in c.execute('SELECT s.title,r.* FROM scan_runs r LEFT JOIN sources s ON s.id=r.source_id ORDER BY r.id DESC LIMIT 30')]}
from app.miniapp import router as miniapp_router
app.include_router(miniapp_router)

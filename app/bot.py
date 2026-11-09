"""Telegram Bot API long polling. No user account actions, only read-only summaries and task status."""
import asyncio, os, logging, html, json, re
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import httpx
try:
    from .main import ROOT, conn, init_db
except ImportError:
    from bootstrap import ROOT as _ROOT
    import sys
    sys.path.insert(0, str(_ROOT))
    from app.main import ROOT, conn, init_db
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
log=logging.getLogger('ayla.bot')
TOKEN=os.getenv('TG_BOT_TOKEN','').strip()
OWNER_IDS={int(v.strip()) for v in os.getenv('TG_BOT_ALLOWED_USER_IDS','').split(',') if v.strip().isdigit()}
WEBAPP_URL=os.getenv('TG_WEBAPP_URL','').strip()
KYIV=ZoneInfo('Europe/Kyiv')

def summary():
    with conn() as c:
        total=c.execute('SELECT COUNT(*) FROM giveaways').fetchone()[0]
        review=c.execute("SELECT COUNT(*) FROM giveaways WHERE review_status='REVIEW'").fetchone()[0]
        entered=c.execute("SELECT COUNT(*) FROM participations WHERE status IN ('ENTERED','AWAITING_RESULT')").fetchone()[0]
    return f'🎁 Ayla Giveaway Hunter\nУсього: {total}\nНа перевірці: {review}\nБеру участь: {entered}'

def latest():
    with conn() as c:
        return [dict(r) for r in c.execute('SELECT id,title,source_url,risk_score FROM giveaways ORDER BY id DESC LIMIT 5')]

def digest_text():
    """A compact on-demand digest; no candidate-by-candidate notifications."""
    current=datetime.now(timezone.utc).isoformat()
    with conn() as c:
        scanned=c.execute('SELECT COUNT(*) FROM raw_items').fetchone()[0]
        pending=c.execute("SELECT COUNT(*) FROM giveaways WHERE review_status='REVIEW' AND (deadline_at IS NULL OR deadline_at>?) AND (winner_at IS NULL OR winner_at>?)",(current,current)).fetchone()[0]
        approved=c.execute("SELECT COUNT(*) FROM giveaways WHERE review_status='APPROVED' AND (deadline_at IS NULL OR deadline_at>?) AND (winner_at IS NULL OR winner_at>?)",(current,current)).fetchone()[0]
        rows=c.execute("""SELECT id,title,source_url,deadline_at FROM giveaways
          WHERE review_status IN ('REVIEW','APPROVED')
          AND (deadline_at IS NULL OR deadline_at>?)
          AND (winner_at IS NULL OR winner_at>?)
          AND (published_at IS NULL OR published_at>=?)
          AND linked_giveaway_id IS NULL
          ORDER BY id DESC LIMIT 5""",(current,current,(datetime.now(timezone.utc)-timedelta(days=7)).isoformat())).fetchall()
    lines=[f'🎁 Ayla Giveaway Hunter · {datetime.now(KYIV):%d.%m %H:%M}',
           f'Перевірено повідомлень: {scanned}',f'На перевірці: {pending} · Підтверджено: {approved}']
    if rows:
        lines.append('\nОстанні актуальні кандидати:')
        for r in rows:lines.append(f"• #{r['id']} {r['title'][:75]}\n{r['source_url']}")
    else:lines.append('\nНових актуальних кандидатів немає.')
    lines.append('\n/review ID — модерація · /dashboard — огляд')
    return '\n'.join(lines)

async def api(client,method,payload):
    r=await client.post(f'https://api.telegram.org/bot{TOKEN}/{method}',json=payload,timeout=40)
    r.raise_for_status()
    data=r.json()
    if not data.get('ok'): raise RuntimeError(str(data.get('description','Bot API error')))
    return data.get('result')

async def respond(client,chat_id,text,markup=None):
    payload={'chat_id':chat_id,'text':text,'disable_web_page_preview':True}
    if markup:payload['reply_markup']=markup
    await api(client,'sendMessage',payload)

async def handle(client,update):
    widget_query=update.get('widget_query')
    message=update.get('message') or update.get('callback_query',{}).get('message')
    if not message and not widget_query:return
    sender=update.get('message',{}).get('from') or update.get('callback_query',{}).get('from') or (widget_query or {}).get('from') or {}
    user_id=sender.get('id')
    chat_id=message['chat']['id'] if message else None
    if not OWNER_IDS or user_id not in OWNER_IDS:
        # Never disclose data to an unconfigured or unauthorized account.
        if update.get('message') and chat_id:
            await respond(client,chat_id,'Доступ закрито. Для налаштування власник може використати Telegram user ID: '+str(user_id))
        return
    if widget_query:
        from app.widget import toggle_task, dashboard_action, dashboard_state, set_widget_status
        data=widget_query.get('data','')
        if re.fullmatch(r't:[0-9]{1,12}',data):
            result=toggle_task(int(data[2:]))
        elif re.fullmatch(r's:[0-9]{1,12}:(ENTERED|WON|LOST)',data):
            _,gid,status=data.split(':')
            result=set_widget_status(int(gid),status)
        elif re.fullmatch(r'(list:[0-3]:[0-9]{1,4}|[arewl]:[0-9]{1,12}:[0-3]:[0-9]{1,4})',data):
            result=dashboard_action(data)
        elif re.fullmatch(r'(text|url):[0-9]{1,12}:[0-3]:[0-9]{1,4}',data):
            kind,gid,tab,page=data.split(':');gid=int(gid)
            with conn() as c:
                row=c.execute('SELECT g.title,g.source_url,g.original_text,r.raw_text FROM giveaways g LEFT JOIN raw_items r ON r.id=g.raw_item_id WHERE g.id=?',(gid,)).fetchone()
            if not row:result={'ok':False,'error':'Запис не знайдено'}
            else:
                if kind=='text':
                    content=(row['original_text'] or row['raw_text'] or 'Оригінальний текст не збережено')
                    # Bot messages limited to 4096 chars; avoid sending excessive text.
                    await respond(client,user_id,f"📄 #{gid}: {row['title'][:120]}\n\n"+content[:3500])
                else:await respond(client,user_id,f"🔗 #{gid}: {row['source_url']}")
                result={'ok':True,'state':dashboard_state(int(tab),int(page))}
        else:result={'ok':False,'error':'Невідома дія'}
        payload=json.dumps(result,ensure_ascii=False,separators=(',',':'))
        if len(payload.encode('utf-8'))>1024:payload='{"ok":false,"error":"Завелика відповідь"}'
        await api(client,'answerWidgetQuery',{'widget_query_id':widget_query['id'],'data':payload})
        return
    raw=(update.get('message',{}).get('text') or '').strip()
    cmd=raw.split(' ',1)[0].split('@')[0].lower()
    if update.get('callback_query'):
        cb=update['callback_query'];data=cb.get('data','')
        await api(client,'answerCallbackQuery',{'callback_query_id':cb['id']})
        if re.fullmatch(r'(approve|reject):[0-9]{1,12}',data):
            action,gid=data.split(':');gid=int(gid)
            with conn() as c:
                old=c.execute('SELECT review_status,title FROM giveaways WHERE id=?',(gid,)).fetchone()
                if not old:await respond(client,chat_id,'Розіграш не знайдено');return
                new='APPROVED' if action=='approve' else 'REJECTED'
                c.execute('UPDATE giveaways SET review_status=? WHERE id=?',(new,gid))
                c.execute('INSERT INTO review_audit(giveaway_id,action,old_value,new_value,created_at) VALUES(?,?,?,?,?)',(gid,'BOT_REVIEW',old['review_status'],new,datetime.now(timezone.utc).isoformat()))
            await respond(client,chat_id,('✅ Підтверджено' if action=='approve' else '❌ Відхилено')+f': #{gid}')
            return
        cmd='/digest' if data=='digest' else '/dashboard'
    if cmd in ('/start','/help'):
        markup={'inline_keyboard':[[{'text':'🎁 Дайджест','callback_data':'digest'},{'text':'📊 Огляд','callback_data':'dashboard'}]]}
        if WEBAPP_URL.startswith('https://'):
            markup['inline_keyboard'].append([{'text':'📱 Відкрити Mini App','web_app':{'url':WEBAPP_URL}}])
        await respond(client,chat_id,'Ayla Giveaway Hunter\n/new — останні 5\n/active — моя участь\n/stats — статистика\n/widget ID — інтерактивна картка\n/review ID — перевірити та вирішити\n/id — мій Telegram ID',markup)
    elif cmd in ('/digest','/new','/latest'):
        await respond(client,chat_id,digest_text())
    elif cmd=='/dashboard':
        if message['chat'].get('type')=='private':
            try:
                from app.widget import dashboard_payload
                await api(client,'sendWidget',dashboard_payload(chat_id))
                return
            except Exception as exc:
                log.warning('Dashboard widget unavailable; fallback to text: %s',str(exc)[:160])
        await respond(client,chat_id,digest_text(),{'inline_keyboard':[[{'text':'🔄 Оновити огляд','callback_data':'dashboard'},{'text':'🎁 Дайджест','callback_data':'digest'}]]})
    elif cmd=='/active':
        with conn() as c:
            rows=c.execute("SELECT g.title,g.source_url FROM giveaways g JOIN participations p ON p.giveaway_id=g.id WHERE p.status IN ('ENTERED','IN_PROGRESS','AWAITING_RESULT') ORDER BY g.id DESC LIMIT 10").fetchall()
        await respond(client,chat_id,'\n\n'.join(f'• {r[0][:100]}\n{r[1]}' for r in rows) if rows else 'Активних участей немає.')
    elif cmd=='/review':
        try:gid=int(raw.split()[1])
        except (IndexError,ValueError):await respond(client,chat_id,'Використання: /review 1');return
        with conn() as c:
            row=c.execute('SELECT title,source_url,review_status,deadline_at,winner_at FROM giveaways WHERE id=?',(gid,)).fetchone()
        if not row:await respond(client,chat_id,'Розіграш не знайдено');return
        markup={'inline_keyboard':[[{'text':'✅ Підтвердити','callback_data':f'approve:{gid}'},{'text':'❌ Відхилити','callback_data':f'reject:{gid}'}]]}
        await respond(client,chat_id,f"🎁 #{gid}: {row['title'][:150]}\nСтатус: {row['review_status']}\nДедлайн: {row['deadline_at'] or '—'}\nВибір переможців: {row['winner_at'] or '—'}\n{row['source_url']}",markup)
    elif cmd=='/widget':
        if message['chat'].get('type')!='private':
            await respond(client,chat_id,'Віджети із завданнями доступні лише у приватному чаті.');return
        from app.widget import widget_payload
        try:
            gid=int(raw.split()[1]);payload=widget_payload(gid,chat_id)
            await api(client,'sendWidget',payload)
        except (IndexError,ValueError):await respond(client,chat_id,'Використання: /widget 1 (ID існуючого розіграшу)')
        except Exception as e:
            log.warning('sendWidget unavailable: %s',e)
            await respond(client,chat_id,'Telegram Widget API недоступний для цього бота/клієнта. Спробуй пізніше або користуйся вебпанеллю.')
    elif cmd=='/id':await respond(client,chat_id,f'Ваш Telegram ID: {user_id}')
    elif cmd=='/stats':await respond(client,chat_id,summary())

async def notification_worker(client):
    """SQLite-backed at-least-once delivery. Dedupe by event_key, recover pending on restart."""
    while True:
        try:
            current=datetime.now(timezone.utc)
            with conn() as c:
                # Upgrade safety: old queued per-candidate alerts must never flood Telegram.
                c.execute("UPDATE notification_outbox SET status='CANCELLED' WHERE status='PENDING' AND event_key LIKE 'new:%'")
                # Enqueue deadline alerts only for approved or entered giveaways.
                rows=c.execute("""SELECT g.id,g.title,g.source_url,g.deadline_at
                    FROM giveaways g LEFT JOIN participations p ON p.giveaway_id=g.id
                    WHERE g.deadline_at IS NOT NULL AND g.review_status='APPROVED'
                    AND COALESCE(p.status,'NEW') NOT IN ('WON','LOST','EXPIRED','SKIPPED','DISQUALIFIED')""").fetchall()
                for g in rows:
                    try:
                        deadline=datetime.fromisoformat(g['deadline_at'].replace('Z','+00:00'))
                        if deadline.tzinfo is None:continue
                        remaining=(deadline-current).total_seconds()
                        for label,seconds in [('24h',86400),('3h',10800),('30m',1800)]:
                            if seconds-900 <= remaining <= seconds:
                                for uid in OWNER_IDS:
                                    key=f'reminder:{label}:{g["id"]}:{g["deadline_at"]}:{uid}'
                                    c.execute('INSERT OR IGNORE INTO notification_outbox(event_key,giveaway_id,chat_id,text,created_at) VALUES(?,?,?,?,?)',
                                              (key,g['id'],uid,f'⏰ До дедлайну {label}: {g["title"][:150]}\n{g["source_url"]}',current.isoformat()))
                    except (ValueError,TypeError):continue
                c.execute("UPDATE notification_outbox SET status='EXPIRED' WHERE status='PENDING' AND event_key LIKE 'reminder:%' AND created_at<?",((current-timedelta(hours=2)).isoformat(),))
                pending=[dict(r) for r in c.execute("""SELECT * FROM notification_outbox WHERE status='PENDING'
                    AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY id LIMIT 10""",(current.isoformat(),))]
            for n in pending:
                try:
                    await respond(client,n['chat_id'],n['text'])
                    with conn() as c:c.execute("UPDATE notification_outbox SET status='SENT',sent_at=?,last_error=NULL WHERE id=?",(datetime.now(timezone.utc).isoformat(),n['id']))
                except Exception as exc:
                    # Permanent errors (blocked bot / invalid chat) stop retrying after 5 attempts.
                    attempts=n['attempts']+1
                    retry=datetime.now(timezone.utc)+timedelta(seconds=min(3600,30*2**min(attempts,7)))
                    with conn() as c:c.execute('UPDATE notification_outbox SET attempts=?,status=?,next_attempt_at=?,last_error=? WHERE id=?',
                                                (attempts,'FAILED' if attempts>=5 else 'PENDING',retry.isoformat(),str(exc)[:250],n['id']))
                    log.warning('Notification delivery failed (id=%s, attempt=%s)',n['id'],attempts)
        except asyncio.CancelledError:raise
        except Exception:log.exception('Notification worker failed')
        await asyncio.sleep(60)

async def run():
    if not TOKEN:raise SystemExit('Set TG_BOT_TOKEN in .env')
    if not OWNER_IDS:raise SystemExit('Set TG_BOT_ALLOWED_USER_IDS in .env; bot will not run open to everyone')
    init_db()
    offset=None
    async with httpx.AsyncClient() as client:
        worker=asyncio.create_task(notification_worker(client))
        try:
            await poll_updates(client)
        finally:
            worker.cancel()
            await asyncio.gather(worker,return_exceptions=True)

async def poll_updates(client):
    offset=None
    while True:
        try:
            result=await api(client,'getUpdates',{'offset':offset,'timeout':25,'allowed_updates':['message','callback_query','widget_query','shared_widget_query']})
            for update in result:
                offset=update['update_id']+1
                try:await handle(client,update)
                except Exception:log.exception('Bot update failed')
        except asyncio.CancelledError:raise
        except Exception:
            log.exception('Bot polling failed; retrying')
            await asyncio.sleep(5)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())

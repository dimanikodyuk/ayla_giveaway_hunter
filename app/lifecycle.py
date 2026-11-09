"""Durable, idempotent result lifecycle. Runs even when Telegram bot is disabled."""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from .main import conn, set_participation_status

log = logging.getLogger('ayla.lifecycle')


def aware(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def reconcile(current=None):
    current = current or datetime.now(timezone.utc)
    closed = reminded = 0
    with conn() as c:
        rows = c.execute('''SELECT g.id,g.title,g.source_url,g.winner_at,p.status
            FROM giveaways g JOIN participations p ON p.giveaway_id=g.id
            WHERE g.winner_at IS NOT NULL AND p.status IN ('ENTERED','AWAITING_RESULT')
            AND g.review_status != 'REJECTED' ''').fetchall()
        owner_ids = [int(x.strip()) for x in os.getenv('TG_BOT_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()]
        for g in rows:
            winner = aware(g['winner_at'])
            if not winner:continue  # never assume a timezone
            elapsed = current - winner.astimezone(timezone.utc)
            if elapsed < timedelta(0):continue
            if elapsed >= timedelta(hours=24):
                if set_participation_status(c,g['id'],'LOST','auto_24h'):
                    closed += 1
            else:
                # Exactly one reminder per giveaway, winner timestamp and recipient.
                for uid in owner_ids:
                    key = f'result:{g["id"]}:{g["winner_at"]}:{uid}'
                    msg = f'🏆 Час перевірити результат розіграшу #{g["id"]}: {g["title"][:140]}\n{g["source_url"]}\nЯкщо виграв — познач WON у віджеті або вебпанелі. Через 24 години після winner_at без підтвердження буде LOST.'
                    cur = c.execute('''INSERT OR IGNORE INTO notification_outbox
                        (event_key,giveaway_id,chat_id,text,created_at) VALUES(?,?,?,?,?)''',
                        (key,g['id'],uid,msg,current.isoformat()))
                    reminded += cur.rowcount
    return {'closed':closed,'reminders_queued':reminded}


async def run():
    while True:
        try:
            result = await asyncio.to_thread(reconcile)
            if result['closed'] or result['reminders_queued']:
                log.info('Lifecycle: %s',result)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Lifecycle failed; retrying')
        await asyncio.sleep(60)

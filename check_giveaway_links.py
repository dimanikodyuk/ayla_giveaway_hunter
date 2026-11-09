"""Read-only audit of likely announcement/native Giveaway groups; no automatic merge."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path(__file__).resolve().parent / 'data' / 'giveaways.sqlite3'
if not DB.exists(): raise SystemExit(f'Базу не знайдено: {DB}')
c = sqlite3.connect(f'file:{DB.as_posix()}?mode=ro', uri=True)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute('SELECT id,title,source_url,published_at,native_giveaway,review_status,deadline_at,winner_at,linked_giveaway_id FROM giveaways ORDER BY id')]
print('Записів:',len(rows),'| зв’язаних:',sum(bool(r['linked_giveaway_id']) for r in rows))
for a in rows:
    if a['native_giveaway'] or not a['published_at']: continue
    try: ta=datetime.fromisoformat(a['published_at'].replace('Z','+00:00'))
    except ValueError: continue
    matches=[]
    for b in rows:
        if not b['native_giveaway'] or not b['published_at']:continue
        if a['source_url'].split('/')[3] != b['source_url'].split('/')[3]:continue
        try: tb=datetime.fromisoformat(b['published_at'].replace('Z','+00:00'))
        except ValueError:continue
        minutes=(tb-ta).total_seconds()/60
        if 0 <= minutes <= 120:matches.append((b['id'],round(minutes,1)))
    if matches:
        print(f"Анонс #{a['id']} {a['title'][:65]} | нативні кандидати: {matches} | {'НЕОДНОЗНАЧНО' if len(matches)>1 else 'потребує підтвердження'}")
print('Дані не змінено. Схожість за часом не доводить, що розіграші однакові.')

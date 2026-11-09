"""Read-only Ayla Giveaway Hunter duplicate audit. Run from project root."""
import sqlite3, pathlib, collections, re, json
from difflib import SequenceMatcher
DB=pathlib.Path('data/giveaways.sqlite3')
if not DB.exists():raise SystemExit('Database not found: '+str(DB.resolve()))
con=sqlite3.connect(f'file:{DB.resolve().as_posix()}?mode=ro',uri=True)
con.row_factory=sqlite3.Row
rows=[dict(x) for x in con.execute('SELECT id,title,source_url,review_status,linked_giveaway_id,published_at,native_giveaway FROM giveaways ORDER BY id')]
print('DB:',DB.resolve(),'giveaways:',len(rows))
print('Linked records:',sum(bool(x['linked_giveaway_id']) for x in rows))
def norm(t):return re.sub(r'\W+',' ',(t or '').lower()).strip()
by_url=collections.defaultdict(list)
for x in rows:by_url[x['source_url'].strip().lower().rstrip('/')].append(x['id'])
print('\nSAME SOURCE URL:')
for url,ids in by_url.items():
 if len(ids)>1:print(ids,url)
print('\nPOSSIBLE DUPLICATES (review manually; not automatically deleted):')
count=0
for i,a in enumerate(rows):
 for b in rows[i+1:]:
  if a['linked_giveaway_id']==b['id'] or b['linked_giveaway_id']==a['id']:continue
  score=SequenceMatcher(None,norm(a['title']),norm(b['title'])).ratio()
  if score>=.82 and min(len(norm(a['title'])),len(norm(b['title'])))>=12:
   print(f"#{a['id']} vs #{b['id']} similarity={score:.2f} | {a['title'][:65]} | {b['title'][:65]}")
   count+=1
print('Pairs:',count)
print('\nBY STATUS:')
for r in con.execute('SELECT review_status,COUNT(*) n FROM giveaways GROUP BY review_status'):print(dict(r))
print('\nPARTICIPATION STATUS:')
for r in con.execute('SELECT status,COUNT(*) n FROM participations GROUP BY status'):print(dict(r))

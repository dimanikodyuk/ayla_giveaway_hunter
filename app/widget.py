"""Telegram Bot API 10.4 widget-sandbox integration (client rollout dependent)."""
import html, json, zlib
from .main import conn, set_participation_status

WIDGET_HTML = '''<!doctype html><html><head><meta charset="utf-8"><style>
body{font:14px sans-serif;color:#e9edf6;background:#17212e;padding:12px;margin:0}
h3{margin:0 0 8px;font-size:17px}p{margin:6px 0;color:#b8c5d5}
button{display:block;width:100%;text-align:left;margin:7px 0;padding:10px;border:1px solid #52637a;border-radius:9px;background:#25364a;color:#fff}
.done{background:#194d3d}#info{font-size:12px;color:#a8c9ff}
</style></head><body><h3 id="title">🎁 Ayla Giveaway Hunter</h3><p id="prize"></p><p id="score"></p><div id="tasks"></div><p id="result"></p><div id="outcomes"></div><p id="info"></p>
<script>
var s={};try{s=JSON.parse(TelegramWidget.chatData||'{}')}catch(e){}
function draw(){document.getElementById('title').textContent='🎁 '+(s.title||'Розіграш');document.getElementById('prize').textContent=s.prize||'';document.getElementById('score').textContent=s.score==null?'':'⭐ AI Giveaway Score: '+s.score+'/100 · '+(s.score_label||'');
var box=document.getElementById('tasks');box.textContent='';(s.tasks||[]).forEach(function(t){var b=document.createElement('button');b.textContent=(t.done?'✓ ':'○ ')+t.text;b.className=t.done?'done':'';
b.addEventListener('click',function(){document.getElementById('info').textContent='Збереження…';TelegramWidget.request('t:'+t.id).then(function(a){try{var v=JSON.parse(a.result);if(v.ok){t.done=v.done;draw();document.getElementById('info').textContent='Збережено'}else{document.getElementById('info').textContent=v.error||'Помилка'}}catch(e){document.getElementById('info').textContent='Некоректна відповідь'}},function(e){document.getElementById('info').textContent='Помилка: '+e.code})});box.appendChild(b)})}
function outcome(status){document.getElementById('info').textContent='Збереження…';TelegramWidget.request('s:'+s.id+':'+status).then(function(a){try{var v=JSON.parse(a.result);if(v.ok){s.status=v.status;draw();drawOutcome();document.getElementById('info').textContent='Збережено'}else document.getElementById('info').textContent=v.error||'Помилка'}catch(e){document.getElementById('info').textContent='Помилка відповіді'}},function(e){document.getElementById('info').textContent='Помилка запиту'})}
function openOriginal(){document.getElementById('info').textContent='Надсилаю посилання в Telegram…';TelegramWidget.request('url:'+s.id+':0:0').then(function(a){try{var r=JSON.parse(a.result||'{}');document.getElementById('info').textContent=r.ok?'Посилання надіслано в особистий чат':'Не вдалося відкрити розіграш'}catch(e){document.getElementById('info').textContent='Помилка відповіді'}},function(){document.getElementById('info').textContent='Помилка запиту'})}
function drawOutcome(){document.getElementById('result').textContent='Мій результат: '+({WON:'🏆 Виграв',LOST:'❌ Не виграв',ENTERED:'Беру участь',AWAITING_RESULT:'Очікую результат'}[s.status]||'Не беру участі');var box=document.getElementById('outcomes');box.textContent='';var open=document.createElement('button');open.textContent='🔗 Перейти до розіграшу';open.onclick=openOriginal;box.appendChild(open);[['ENTERED','🙋 Беру участь'],['WON','🏆 Я виграв'],['LOST','❌ Не виграв']].forEach(function(x){var b=document.createElement('button');b.textContent=x[1];b.onclick=function(){outcome(x[0])};box.appendChild(b)})}
TelegramWidget.onEvent('chatDataChanged',function(){try{s=JSON.parse(TelegramWidget.chatData||'{}')}catch(e){}draw();drawOutcome()});draw();drawOutcome();
</script></body></html>'''

def widget_state(gid):
    with conn() as c:
        row=c.execute("SELECT g.*,COALESCE(p.status,'NEW') AS status,COALESCE(g.original_text,r.raw_text,'') AS content,(SELECT COUNT(*) FROM tasks t WHERE t.giveaway_id=g.id) AS task_count FROM giveaways g LEFT JOIN participations p ON p.giveaway_id=g.id LEFT JOIN raw_items r ON r.id=g.raw_item_id WHERE g.id=?",(gid,)).fetchone()
        if row is None:raise ValueError('Giveaway not found')
        tasks=[{'id':r['id'],'text':r['description'][:90],'done':bool(r['completed'])} for r in c.execute('SELECT t.id,t.description,COALESCE(p.completed,0) completed FROM tasks t LEFT JOIN task_progress p ON p.task_id=t.id WHERE t.giveaway_id=? ORDER BY t.sort_order,t.id LIMIT 10',(gid,))]
    from .intelligence import giveaway_score
    score=giveaway_score(dict(row),row['content'])
    state={'id':gid,'title':row['title'][:90],'prize':row['prize'][:80],'status':row['status'],'tasks':tasks,'score':score['score'],'score_label':score['label']}
    while len(json.dumps(state,ensure_ascii=False).encode())>1000 and tasks:tasks.pop()
    return json.dumps(state,ensure_ascii=False,separators=(',',':'))

def widget_payload(gid,chat_id):
    data=widget_state(gid)
    if len(WIDGET_HTML.encode())>32768 or len(zlib.compress(WIDGET_HTML.encode(),9))>4096:raise ValueError('Widget exceeds sandbox limits')
    return {'chat_id':chat_id,'html':WIDGET_HTML,'width':340,'height':0,'chat_data':data,'caption':f'🎁 Розіграш #{gid} · Ayla Giveaway Hunter','allow_queries':True,'is_shared':False}

def toggle_task(task_id):
    from .main import now
    with conn() as c:
        row=c.execute('SELECT COALESCE(p.completed,0) completed FROM tasks t LEFT JOIN task_progress p ON p.task_id=t.id WHERE t.id=?',(task_id,)).fetchone()
        if not row:return {'ok':False,'error':'Завдання не знайдено'}
        done=not bool(row['completed'])
        c.execute('INSERT INTO task_progress(task_id,completed,completed_at) VALUES(?,?,?) ON CONFLICT(task_id) DO UPDATE SET completed=excluded.completed,completed_at=excluded.completed_at',(task_id,int(done),now() if done else None))
    return {'ok':True,'done':done}

DASHBOARD_HTML = '<!doctype html><html lang="uk"><head><meta charset="utf-8"><style>\n:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;padding:12px;background:#edf2ef;color:#142820;font:14px/1.45 system-ui,-apple-system,sans-serif}h2{font-size:19px;margin:0;color:#122c21}.sub{font-size:12px;color:#41584c}.stats{display:flex;gap:8px;margin:12px 0}.stat{flex:1;background:#193a2d;color:#fff;border-radius:12px;padding:11px 8px;min-width:0}.stat b{display:block;color:#ffdc76;font-size:24px;line-height:1.1}.stat small{font-size:11px;color:#f0f8f3;line-height:1.25;display:block;margin-top:5px}nav{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin:12px 0}button{font:inherit;border:1px solid #aebdb4;border-radius:9px;background:#fff;color:#183b2c;padding:10px 6px;font-weight:650;cursor:pointer}nav button{font-size:11px;padding:11px 2px;overflow-wrap:anywhere}.active{background:#193e2d;color:white;border-color:#193e2d}.item{background:white;border:1px solid #c4d1c8;border-radius:13px;padding:13px;margin:10px 0;box-shadow:0 2px 5px #142c1910}.item strong{display:block;font-size:14px;line-height:1.35;margin-bottom:7px;color:#172c23}.meta{white-space:pre-line;font-size:12px;line-height:1.6;color:#365348}.actions{display:flex;gap:7px;margin-top:11px}.actions button{flex:1;font-size:12px;min-height:40px}.yes{background:#d7f3df;color:#16562e;border-color:#77b78c}.no{background:#ffebeb;color:#842626;border-color:#e5a4a4}.link{background:#dce9ff;color:#123c7d;border-color:#93b6ed}.pager{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:12px 0}.pager button{padding:9px 12px}.pager button:disabled{opacity:.46;background:#e1e7e2;color:#506357}.empty{background:white;padding:22px 12px;text-align:center;border-radius:12px;color:#355746;border:1px solid #cad8cf}#msg{font-size:12px;min-height:17px;color:#244d35}#filter{width:100%;border:1px solid #a6bcae;border-radius:9px;padding:9px 10px;background:white;color:#183b2c;font:inherit;margin-bottom:7px}</style></head><body><h2>🎁 Ayla Giveaway Hunter</h2><div class="sub">Твої розіграші та найближчі події</div><div class="stats"><div class="stat"><b id="all">0</b><small>Знайдено</small></div><div class="stat"><b id="pending">0</b><small>На перевірці</small></div><div class="stat"><b id="entered">0</b><small>Беру участь</small></div></div><nav><button id="b0">🎁 Участь</button><button id="b1">🔎 Перевірка</button><button id="b2">📅 Дати</button><button id="b3">📊 Канали</button></nav><select id="filter"><option value="all">Усі записи</option><option value="dated">З відомою датою</option><option value="unknown">Дата невідома</option></select><div id="items"></div><div class="pager"><button id="prev">← Назад</button><span class="sub" id="page"></span><button id="next">Далі →</button></div><div id="msg"></div><script>\nvar state={n:0,p:0,e:0,rows:[],total:0},tab=0,page=0,filter=\'all\';\ntry{state=JSON.parse(TelegramWidget.chatData||\'{}\')}catch(e){}\nfunction el(tag,cls,t){var x=document.createElement(tag);if(cls)x.className=cls;if(t!==undefined)x.textContent=t;return x}\nfunction req(cmd){document.getElementById(\'msg\').textContent=\'Завантаження…\';TelegramWidget.request(cmd).then(function(v){try{var r=JSON.parse(v.result||\'{}\');if(r.ok){state=r.state;draw();document.getElementById(\'msg\').textContent=\'\'}else document.getElementById(\'msg\').textContent=r.error||\'Помилка\'}catch(e){document.getElementById(\'msg\').textContent=\'Помилка відповіді\'}},function(e){document.getElementById(\'msg\').textContent=\'Недоступно: \'+(e.code||\'помилка\')})}\nfunction draw(){document.getElementById(\'all\').textContent=state.n||0;document.getElementById(\'pending\').textContent=state.p||0;document.getElementById(\'entered\').textContent=state.e||0;for(var i=0;i<4;i++)document.getElementById(\'b\'+i).className=i===tab?\'active\':\'\';var box=document.getElementById(\'items\');box.textContent=\'\';(state.rows||[]).filter(function(r){return filter===\'all\'||(filter===\'dated\'?r.hasDate:!r.hasDate)}).forEach(function(r){var c=el(\'div\',\'item\');c.appendChild(el(\'strong\',\'\',(r.score==null?\'\':\'⭐ \'+r.score+\'/100 · \')+(r.t||\'Розіграш\')));c.appendChild(el(\'div\',\'meta\',r.info||\'\'));var a=el(\'div\',\'actions\');if(tab===1&&r.review===\'REVIEW\'){var y=el(\'button\',\'yes\',\'✓ Підтвердити\'),n=el(\'button\',\'no\',\'✕ Відхилити\');y.onclick=function(){req(\'a:\'+r.id+\':\'+tab+\':\'+page)};n.onclick=function(){req(\'r:\'+r.id+\':\'+tab+\':\'+page)};a.appendChild(y);a.appendChild(n)}if(tab!==3){var full=el(\'button\',\'link\',\'📄 Текст\'),original=el(\'button\',\'link\',\'↗ Оригінал\');full.onclick=function(){req(\'text:\'+r.id+\':\'+tab+\':\'+page)};original.onclick=function(){req(\'url:\'+r.id+\':\'+tab+\':\'+page)};a.appendChild(full);a.appendChild(original)}if(tab!==3){if(![\'ENTERED\',\'AWAITING_RESULT\',\'WON\',\'LOST\'].includes(r.status)){var enter=el(\'button\',\'yes\',\'🙋 Беру участь\');enter.onclick=function(){req(\'e:\'+r.id+\':\'+tab+\':\'+page)};a.appendChild(enter)}var won=el(\'button\',\'yes\',\'🏆 Виграв\'),lost=el(\'button\',\'no\',\'❌ Програв\');won.onclick=function(){req(\'w:\'+r.id+\':\'+tab+\':\'+page)};lost.onclick=function(){req(\'l:\'+r.id+\':\'+tab+\':\'+page)};a.appendChild(won);a.appendChild(lost)}c.appendChild(a);box.appendChild(c)});if(!(state.rows||[]).length)box.appendChild(el(\'p\',\'empty\',tab===1?\'Усі розіграші перевірено\':\'Записів немає\'));document.getElementById(\'filter\').style.display=tab===3?\'none\':\'block\';document.getElementById(\'page\').textContent=(page+1)+\' / \'+Math.max(1,Math.ceil((state.total||0)/3));document.getElementById(\'prev\').disabled=page===0;document.getElementById(\'next\').disabled=(page+1)*3>=(state.total||0)}\ndocument.getElementById(\'filter\').onchange=function(){filter=this.value;draw()};for(let i=0;i<4;i++)document.getElementById(\'b\'+i).onclick=function(){tab=i;page=0;filter=\'all\';document.getElementById(\'filter\').value=\'all\';req(\'list:\'+tab+\':0\')};document.getElementById(\'prev\').onclick=function(){if(page){page--;req(\'list:\'+tab+\':\'+page)}};document.getElementById(\'next\').onclick=function(){page++;req(\'list:\'+tab+\':\'+page)};TelegramWidget.onEvent(\'chatDataChanged\',function(){try{state=JSON.parse(TelegramWidget.chatData||\'{}\');draw()}catch(e){}});draw();\n</script></body></html>'
def dashboard_state(tab=0,page=0):
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    tab=max(0,min(3,int(tab)));page=max(0,min(10000,int(page)))
    with conn() as c:
        n=c.execute('SELECT COUNT(*) FROM giveaways').fetchone()[0]
        p=c.execute("SELECT COUNT(*) FROM giveaways WHERE review_status='REVIEW'").fetchone()[0]
        e=c.execute("SELECT COUNT(*) FROM participations p JOIN giveaways g ON g.id=p.giveaway_id WHERE p.status IN ('IN_PROGRESS','ENTERED','AWAITING_RESULT') AND g.review_status!='REJECTED'").fetchone()[0]
        base="FROM giveaways g LEFT JOIN participations p ON p.giveaway_id=g.id "
        if tab==0:where="WHERE p.status IN ('IN_PROGRESS','ENTERED','AWAITING_RESULT') AND g.review_status!='REJECTED'"
        elif tab==1:where="WHERE g.review_status='REVIEW' AND g.linked_giveaway_id IS NULL"
        elif tab==2:where="WHERE (g.deadline_at IS NOT NULL OR g.winner_at IS NOT NULL) AND g.review_status!='REJECTED'"
        else:
            total=c.execute('SELECT COUNT(*) FROM sources').fetchone()[0]
            rows=c.execute('SELECT s.title,COUNT(DISTINCT g.id) cnt FROM sources s LEFT JOIN raw_items r ON r.source_id=s.id LEFT JOIN giveaways g ON g.raw_item_id=r.id GROUP BY s.id ORDER BY cnt DESC,s.id LIMIT 3 OFFSET ?', (page*3,)).fetchall()
            return {'n':n,'p':p,'e':e,'total':total,'rows':[{'t':r['title'][:50],'info':'Знайдено: '+str(r['cnt'])} for r in rows]}
        total=c.execute('SELECT COUNT(*) '+base+where).fetchone()[0]
        order='CASE WHEN COALESCE(g.deadline_at,g.winner_at) IS NULL THEN 1 ELSE 0 END, COALESCE(g.deadline_at,g.winner_at) ASC, g.id DESC' if tab in (0,2) else 'g.id DESC'
        rows=c.execute("SELECT g.*,p.status,COALESCE(g.original_text,r.raw_text,'') AS content,(SELECT COUNT(*) FROM tasks t WHERE t.giveaway_id=g.id) AS task_count "+base+" LEFT JOIN raw_items r ON r.id=g.raw_item_id "+where+' ORDER BY '+order+' LIMIT 3 OFFSET ?', (page*3,)).fetchall()
    labels={'NEW':'Новий','IN_PROGRESS':'Виконую умови','ENTERED':'Беру участь',
      'AWAITING_RESULT':'Очікую результат','WON':'Переміг','LOST':'Не виграв',
      'EXPIRED':'Завершено','UNKNOWN':'Статус невідомий','SKIPPED':'Пропущено',
      'DISQUALIFIED':'Дискваліфіковано','REVIEW':'Потребує перевірки',
      'APPROVED':'Підтверджено','REJECTED':'Відхилено'}
    def kyiv(value):
        if not value:return None
        try:
            dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo('Europe/Kyiv')).strftime('%d.%m.%Y, %H:%M')
        except (ValueError,TypeError,KeyError):return 'Дата не визначена'
    result={'n':n,'p':p,'e':e,'total':total,'rows':[]}
    for r in rows:
        details=['№'+str(r['id']),labels.get(r['status'] or r['review_status'], 'Статус невідомий')]
        if r['deadline_at']:details.append('Дедлайн: '+kyiv(r['deadline_at']))
        if r['winner_at']:details.append('Переможці: '+kyiv(r['winner_at']))
        if not r['deadline_at'] and not r['winner_at']:details.append('Дату не вказано')
        from .intelligence import giveaway_score
        score=giveaway_score(dict(r),r['content'])
        result['rows'].append({'id':r['id'],'score':score['score'],'t':(r['title'] or '')[:70],
          'review':r['review_status'],'status':r['status'] or 'NEW','hasDate':bool(r['deadline_at'] or r['winner_at']),'info':' · '.join(details[:2])+'\n'+'\n'.join(details[2:])})
    # Widget query reply and chat_data have strict byte limits. Trim labels, never return invalid JSON.
    def size():return len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    while size()>850 and result['rows']:
        longest=max(result['rows'],key=lambda r:len(r['t']))
        if len(longest['t'])>18:longest['t']=longest['t'][:-10]
        else:result['rows'].pop()
    return result

def dashboard_payload(chat_id):
    data=json.dumps(dashboard_state(),ensure_ascii=False,separators=(',',':'))
    if len(DASHBOARD_HTML.encode())>32768 or len(zlib.compress(DASHBOARD_HTML.encode(),9))>4096:raise ValueError('Dashboard exceeds Telegram limits')
    return {'chat_id':chat_id,'html':DASHBOARD_HTML,'width':360,'height':0,'chat_data':data,'allow_queries':True,'is_shared':False,'caption':'🎁 Ayla Giveaway Hunter · Dashboard'}

def dashboard_action(command):
    import re
    from datetime import datetime,timezone
    m=re.fullmatch(r'list:([0-3]):([0-9]{1,4})',command)
    if m:return {'ok':True,'state':dashboard_state(int(m[1]),int(m[2]))}
    m=re.fullmatch(r'([ewl]):([0-9]{1,12}):([0-3]):([0-9]{1,4})',command)
    if m:
        action,gid,tab,page=m[1],int(m[2]),int(m[3]),int(m[4])
        new={'e':'ENTERED','w':'WON','l':'LOST'}[action]
        with conn() as c:
            if not set_participation_status(c,gid,new,'widget'):
                return {'ok':False,'error':'Запис не знайдено'}
        return {'ok':True,'state':dashboard_state(tab,page)}
    m=re.fullmatch(r'([ar]):([0-9]{1,12}):([0-3]):([0-9]{1,4})',command)
    if not m:return {'ok':False,'error':'Невідома дія'}
    action,gid,tab,page=m[1],int(m[2]),int(m[3]),int(m[4])
    with conn() as c:
        old=c.execute('SELECT review_status FROM giveaways WHERE id=?',(gid,)).fetchone()
        if not old:return {'ok':False,'error':'Запис не знайдено'}
        if old['review_status']!='REVIEW':return {'ok':False,'error':'Запис уже перевірено'}
        new='APPROVED' if action=='a' else 'REJECTED'
        c.execute('UPDATE giveaways SET review_status=? WHERE id=?',(new,gid))
        c.execute('INSERT INTO review_audit(giveaway_id,action,old_value,new_value,created_at) VALUES(?,?,?,?,?)',(gid,'WIDGET_REVIEW',old['review_status'],new,datetime.now(timezone.utc).isoformat()))
    return {'ok':True,'state':dashboard_state(tab,page)}


def set_widget_status(gid,status):
    if status not in ('ENTERED','WON','LOST'):
        return {'ok':False,'error':'Невідомий статус'}
    with conn() as c:
        if not set_participation_status(c,gid,status,'widget'):
            return {'ok':False,'error':'Запис не знайдено'}
    return {'ok':True,'status':status}

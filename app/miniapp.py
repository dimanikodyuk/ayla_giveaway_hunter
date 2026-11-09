"""Telegram Mini App authorization using Telegram WebApp initData HMAC."""
import os,hmac,hashlib,json,time
from urllib.parse import parse_qsl
from fastapi import APIRouter,HTTPException,Header
from fastapi.responses import FileResponse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def conn():
    # Resolve lazily: importing this router must never re-import app.main.
    from app.main import conn as db_conn
    return db_conn()
router=APIRouter()

def verify_init_data(value,token=None,allowed=None,now=None):
    token=token if token is not None else os.getenv('TG_BOT_TOKEN','')
    allowed=allowed if allowed is not None else {int(x.strip()) for x in os.getenv('TG_BOT_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}
    if not token or not allowed or not value or len(value)>8192:raise ValueError('Not configured or missing initData')
    fields=dict(parse_qsl(value,keep_blank_values=True,strict_parsing=True))
    signature=fields.pop('hash','')
    if not signature or len(signature)!=64:raise ValueError('Invalid hash')
    check='\n'.join(f'{k}={v}' for k,v in sorted(fields.items()))
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):raise ValueError('Invalid signature')
    timestamp=int(fields.get('auth_date','0'))
    current=int(time.time()) if now is None else now
    if timestamp>current+60 or current-timestamp>3600:raise ValueError('Expired initData')
    user=json.loads(fields.get('user','{}'))
    if user.get('id') not in allowed:raise ValueError('User not allowed')
    return user

@router.get('/miniapp')
def miniapp():return FileResponse(ROOT/'app'/'static'/'miniapp.html')

@router.get('/api/miniapp/giveaways')
def miniapp_giveaways(x_telegram_init_data:str=Header(default='')):
    try:user=verify_init_data(x_telegram_init_data)
    except (ValueError,TypeError,KeyError,json.JSONDecodeError):raise HTTPException(401,'Telegram Mini App authorization failed')
    with conn() as c:
        rows=[dict(r) for r in c.execute('SELECT g.id,g.title,g.prize,g.source_url,g.review_status,g.risk_score,p.status AS participation_status FROM giveaways g LEFT JOIN participations p ON p.giveaway_id=g.id ORDER BY g.id DESC LIMIT 100')]
        for r in rows:r['tasks']=[dict(t) for t in c.execute('SELECT t.id,t.description,COALESCE(tp.completed,0) AS completed FROM tasks t LEFT JOIN task_progress tp ON tp.task_id=t.id WHERE t.giveaway_id=? ORDER BY t.sort_order',(r['id'],))]
    return {'items':rows,'user_id':user['id']}

from pydantic import BaseModel
class Completion(BaseModel):completed:bool
@router.patch('/api/miniapp/tasks/{task_id}')
def miniapp_task(task_id:int,data:Completion,x_telegram_init_data:str=Header(default='')):
    try:verify_init_data(x_telegram_init_data)
    except (ValueError,TypeError,KeyError,json.JSONDecodeError):raise HTTPException(401,'Telegram Mini App authorization failed')
    from app.main import now
    with conn() as c:
        if not c.execute('SELECT 1 FROM tasks WHERE id=?',(task_id,)).fetchone():raise HTTPException(404,'Task not found')
        c.execute('INSERT INTO task_progress(task_id,completed,completed_at) VALUES(?,?,?) ON CONFLICT(task_id) DO UPDATE SET completed=excluded.completed,completed_at=excluded.completed_at',(task_id,int(data.completed),now() if data.completed else None))
    return {'ok':True}

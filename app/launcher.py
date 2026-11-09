"""Single entry point for PyCharm and command line: python app/launcher.py"""
import sys,os,asyncio,logging
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from app.main import app,init_db
from app.collector import run as collect
from app.bot import run as bot
import uvicorn

async def run_all():
    init_db()
    config=uvicorn.Config(app,host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','8093')),log_level='info')
    jobs=[asyncio.create_task(uvicorn.Server(config).serve(),name='web')]
    if os.getenv('ENABLE_COLLECTOR','true').lower()=='true':jobs.append(asyncio.create_task(collect(),name='collector'))
    if os.getenv('ENABLE_BOT','false').lower()=='true':jobs.append(asyncio.create_task(bot(),name='bot'))
    try:
        done,pending=await asyncio.wait(jobs,return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if t.exception():raise t.exception()
    finally:
        for t in jobs:t.cancel()
        await asyncio.gather(*jobs,return_exceptions=True)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:asyncio.run(run_all())
    except KeyboardInterrupt:pass

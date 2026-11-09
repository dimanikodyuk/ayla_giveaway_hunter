import asyncio,os
from telethon import TelegramClient
try:
    from .main import ROOT
except ImportError:
    from bootstrap import ROOT as _ROOT
    import sys
    sys.path.insert(0, str(_ROOT))
    from app.main import ROOT
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
async def main():
    api_id=os.getenv('TG_API_ID');api_hash=os.getenv('TG_API_HASH')
    if not api_id or not api_hash:raise SystemExit('Set TG_API_ID and TG_API_HASH in .env')
    (ROOT/'data').mkdir(exist_ok=True)
    async with TelegramClient(str(ROOT/'data'/'telegram_user'),int(api_id),api_hash) as client:
        me=await client.get_me();print('Authorized Telegram user ID:',me.id)
if __name__=='__main__':asyncio.run(main())

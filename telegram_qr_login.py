"""Ayla Giveaway Hunter: Telegram user QR login (Telethon 1.x).
Run from the project root with Python in your virtual environment.
"""
import asyncio
import getpass
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, errors

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')


async def main():
    api_id = os.getenv('TG_API_ID', '').strip()
    api_hash = os.getenv('TG_API_HASH', '').strip()
    if not api_id.isdigit() or not api_hash:
        raise SystemExit('Set TG_API_ID and TG_API_HASH in the project .env first.')

    data_dir = ROOT / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    session_path = data_dir / 'telegram_user'

    client = TelegramClient(str(session_path), int(api_id), api_hash)
    await client.connect()
    try:
        me = await client.get_me()
        if me:
            if me.bot:
                raise SystemExit('Existing telegram_user.session belongs to a BOT. Stop the collector, rename that session file, and retry.')
            print(f'Already authorized as USER (ID {me.id}). Nothing to do.')
            return

        try:
            import qrcode
        except ImportError:
            raise SystemExit('Install QR support: .\\.venv\\Scripts\\python.exe -m pip install qrcode[pil]')

        print('On iPhone: Telegram > Settings > Devices > Link Desktop Device.')
        print('Scan the QR from your PC screen. Never share the QR or the session file.')
        while True:
            qr_login = await client.qr_login()
            qr_file = data_dir / 'telegram_login_qr.png'
            qrcode.make(qr_login.url).save(qr_file)
            print(f'\nQR saved locally: {qr_file}')
            print('Open the PNG on your PC. QR expires quickly; refresh if necessary.')
            try:
                await qr_login.wait(timeout=45)
                break
            except asyncio.TimeoutError:
                print('QR expired. Generating a fresh one...')
            except errors.SessionPasswordNeededError:
                password = getpass.getpass('Telegram 2FA password (hidden): ')
                await client.sign_in(password=password)
                break
            finally:
                try:
                    qr_file.unlink(missing_ok=True)
                except OSError:
                    pass

        me = await client.get_me()
        if not me or me.bot:
            raise RuntimeError('Expected a user session, but Telegram did not return a user account.')
        print(f'\nSUCCESS: Authorized=True, Is bot=False, User ID={me.id}')
        print(f'Session saved locally: {session_path}.session')
    finally:
        await client.disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nCancelled.')

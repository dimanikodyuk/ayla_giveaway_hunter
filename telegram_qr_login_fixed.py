"""Ayla Giveaway Hunter - QR login for a Telegram USER account (Telethon 1.x).

Run from the project root: python telegram_qr_login_fixed.py
Requires: telethon, python-dotenv, qrcode[pil].
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
    if not api_id.isdecimal() or not api_hash:
        raise SystemExit('Missing TG_API_ID or TG_API_HASH in .env')

    import qrcode

    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    session = data / 'telegram_user'
    qr_path = data / 'telegram_login_qr.png'

    client = TelegramClient(str(session), int(api_id), api_hash)
    await client.connect()  # Do NOT use client.start() or async with TelegramClient.
    try:
        me = await client.get_me()
        if me is not None:
            if me.bot:
                raise RuntimeError('telegram_user.session is a BOT session. Stop launcher, rename the session file and retry.')
            print(f'Already authorized: user account ID={me.id}, is_bot=False', flush=True)
            return

        print('iPhone: Telegram > Settings > Devices > Link Desktop Device.', flush=True)
        print('Scan the QR and CONFIRM the login on the iPhone.', flush=True)
        print('Keep this script running until SUCCESS appears.', flush=True)
        qr = await client.qr_login()
        for attempt in range(1, 8):
            if attempt > 1:
                await qr.recreate()
            qrcode.make(qr.url).save(qr_path)
            print(f'\nQR attempt {attempt}/7: {qr_path}', flush=True)
            print('Open the CURRENT PNG and confirm on iPhone. Waiting up to 60 seconds...', flush=True)
            try:
                await qr.wait(timeout=60)
                print('Telegram confirmed QR login.', flush=True)
                break
            except asyncio.TimeoutError:
                print('No confirmation received. Refreshing QR...', flush=True)
            except errors.SessionPasswordNeededError:
                print('Two-step verification is enabled.', flush=True)
                await client.sign_in(password=getpass.getpass('Telegram 2FA password (hidden): '))
                break
        else:
            print('Login not confirmed. Check iPhone confirmation screen and Telegram > Devices.', flush=True)
            return

        me = await client.get_me()
        if me is None or me.bot:
            raise RuntimeError('QR login did not produce a USER session.')
        print(f'SUCCESS: Authorized=True, Is bot=False, User ID={me.id}', flush=True)
        print(f'Session: {session}.session', flush=True)
    finally:
        await client.disconnect()
        # Do not delete the PNG while it may still be open on Windows.
        # The QR is short-lived and should be treated as a secret.


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nStopped by user.')

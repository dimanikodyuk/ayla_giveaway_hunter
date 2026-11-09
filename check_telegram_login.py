import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

async def main():
    client = TelegramClient(
        "data/telegram_login_check",
        int(os.environ["TG_API_ID"]),
        os.environ["TG_API_HASH"],
    )

    await client.connect()

    try:
        phone = input("Phone (+380...): ").strip()
        result = await client.send_code_request(phone)

        print("Code delivery type:", type(result.type).__name__)
        print("Timeout:", getattr(result, "timeout", None))
        print("Next type:", type(result.next_type).__name__
              if getattr(result, "next_type", None) else None)
    finally:
        await client.disconnect()

asyncio.run(main())
import asyncio
import os

from geminiclient import GeminiClient
from bot import TelegramBot

async def main():
    bot_token = os.getenv("BOT_TOKEN")
    api_key = os.getenv("API_KEY")
    
    if not bot_token or not api_key:
        raise RuntimeError("❌ Немає токенів")

    client = GeminiClient()
    bot = TelegramBot(client, bot_token)
    
    await bot.start_polling()


asyncio.run(main())
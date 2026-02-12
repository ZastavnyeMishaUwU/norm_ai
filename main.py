import asyncio
import os

from geminiclient import GeminiClient
from bot import TelegramBot

async def health_server():
    port = int(os.getenv("PORT", "10000"))

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            await reader.readline()
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
        except:
            pass

        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    print(f"🌐 Health server: порт {port}")
    async with server:
        await server.serve_forever()

async def main():
    bot_token = os.getenv("BOT_TOKEN")
    api_key = os.getenv("API_KEY")
    
    if not bot_token:
        raise RuntimeError("❌ BOT_TOKEN не знайдено")
    if not api_key:
        raise RuntimeError("❌ API_KEY не знайдено")

    print("🚀 Запуск бота 12-го ліцею...")
    
    client = GeminiClient()
    tg_bot = TelegramBot(client, bot_token)

    await asyncio.gather(
        tg_bot.start_polling(),
        health_server(),
    )

if __name__ == "__main__":
    asyncio.run(main())
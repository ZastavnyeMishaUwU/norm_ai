import asyncio
import os
from geminiclient import GeminiClient
from bot import TelegramBot

async def health_server():
    # Читаємо порт зі змінної оточення, яку задає Render. Якщо її немає (наприклад, локально), використовуємо 10000.
    port = int(os.getenv("PORT", 10000))
    # Важливо слухати на всіх інтерфейсах (0.0.0.0), а не тільки localhost
    host = "0.0.0.0"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        # Це найпростіший обробник, який просто повертає "OK"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, host, port)
    print(f"🌐 Health server запущено на {host}:{port}")
    async with server:
        await server.serve_forever()

async def main():
    bot_token = os.getenv("BOT_TOKEN")
    api_key = os.getenv("API_KEY")

    if not bot_token or not api_key:
        raise RuntimeError("❌ BOT_TOKEN або API_KEY не знайдено в змінних оточення")

    print("🚀 Запуск бота...")
    client = GeminiClient()
    tg_bot = TelegramBot(client, bot_token)

    # Запускаємо одночасно бота і HTTP-сервер для health checks
    await asyncio.gather(
        tg_bot.start_polling(),
        health_server(),
    )

if __name__ == "__main__":
    asyncio.run(main())
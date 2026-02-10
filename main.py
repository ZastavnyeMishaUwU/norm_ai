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

        body = b"OK"
        resp = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            + body
        )
        writer.write(resp)
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    print(f"Health server on :{port}")
    async with server:
        await server.serve_forever()


async def main():
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("ENV BOT_TOKEN is empty")
    
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("ENV API_KEY is empty")

    print("Запуск бота 12-го ліцею...")

    client = GeminiClient()
    tg_bot = TelegramBot(client, bot_token)

    await asyncio.gather(
        tg_bot.start_polling(),
        health_server(),
    )


if __name__ == "__main__":
    asyncio.run(main())
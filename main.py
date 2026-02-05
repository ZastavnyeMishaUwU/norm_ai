import asyncio
import os


def load_dotenv_simple(path: str = ".env"):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # не перетираємо якщо вже є в env
                os.environ.setdefault(k, v)
    except:
        pass


async def main():
    load_dotenv_simple(".env")

    from geminiclient import GeminiClient
    from bot import TelegramBot

    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TG_BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN (або TG_BOT_TOKEN) не заданий в env/.env")

    ai_client = GeminiClient()
    tg_bot = TelegramBot(ai_client, bot_token)
    await tg_bot.start_polling()


if __name__ == "__main__":
    asyncio.run(main())

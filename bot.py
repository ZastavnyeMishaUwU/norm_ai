import asyncio
import re
from collections import defaultdict

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

MAX_LEN = 3900
SHORT_MAX_TOKENS = 420
DETAIL_MAX_TOKENS = 900

SHORT_MAX_CHARS = 900
DETAIL_MAX_CHARS = 2200


def split_chunks(text: str, size: int = MAX_LEN):
    text = text or ""
    for i in range(0, len(text), size):
        yield text[i:i + size]


def normalize_bold(md: str) -> str:
    # Gemini любить **bold**, Telegram Markdown часто краще пережовує *bold*
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", md or "")


async def send_markdown_safe(bot: Bot, chat_id: int, text: str, reply_markup=None):
    text = normalize_bold(text)

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return
    except TelegramBadRequest:
        pass

    # fallback plain text
    plain = re.sub(r"[*_`]", "", text)
    await bot.send_message(
        chat_id=chat_id,
        text=plain,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


class TelegramBot:
    def __init__(self, client, token: str):
        self.client = client
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()

        self.user_locks = defaultdict(asyncio.Lock)
        self.user_state = {}  # user_id -> {"detail_next": bool, "pending_detail_q": str|None}

        self.setup_handlers()
        self.dp.include_router(self.router)

    def state(self, user_id: int):
        if user_id not in self.user_state:
            self.user_state[user_id] = {
                "detail_next": False,
                "pending_detail_q": None,
            }
        return self.user_state[user_id]

    def get_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Програміст"), KeyboardButton(text="Асистент")],
                [KeyboardButton(text="Детально (1 раз)"), KeyboardButton(text="Режими")],
                [KeyboardButton(text="Очистити")],
            ],
            resize_keyboard=True
        )

    def setup_handlers(self):
        @self.router.message(Command("start"))
        async def start_cmd(message: Message):
            st = self.state(message.from_user.id)
            st["detail_next"] = False
            st["pending_detail_q"] = None

            await message.answer(
                "Привіт. Вибери режим або пиши питання.",
                reply_markup=self.get_keyboard(),
            )

        @self.router.message(Command("modes"))
        async def modes_cmd(message: Message):
            modes = self.client.get_available_modes()
            if not modes:
                await message.answer("Режимів немає. Додай .txt файли в папку instructions/.")
                return
            await message.answer("Доступні режими:\n" + "\n".join(f"- {m}" for m in modes))

        @self.router.message(F.text == "Режими")
        async def modes_btn(message: Message):
            modes = self.client.get_available_modes()
            if not modes:
                await message.answer("Режимів немає. Додай .txt файли в папку instructions/.")
                return
            await message.answer("Доступні режими:\n" + "\n".join(f"- {m}" for m in modes))

        @self.router.message(F.text == "Програміст")
        async def programmer_mode(message: Message):
            # підтримує твою стару логіку: teach
            ok = self.client.set_mode("teach")
            await message.answer(
                f"Режим: teach" + ("" if ok else " (нема інструкції, але режим встановлено)"),
                reply_markup=self.get_keyboard()
            )

        @self.router.message(F.text == "Асистент")
        async def assistant_mode(message: Message):
            ok = self.client.set_mode("assistant")
            await message.answer(
                f"Режим: assistant" + ("" if ok else " (нема інструкції, але режим встановлено)"),
                reply_markup=self.get_keyboard()
            )

        @self.router.message(F.text == "Детально (1 раз)")
        async def detail_once(message: Message):
            st = self.state(message.from_user.id)
            st["detail_next"] = True
            await message.answer("Ок. Наступна відповідь буде детально.", reply_markup=self.get_keyboard())

        @self.router.message(F.text == "Очистити")
        async def clear_state(message: Message):
            st = self.state(message.from_user.id)
            st["detail_next"] = False
            st["pending_detail_q"] = None
            await message.answer("Ок. Скинув контекст (локально).", reply_markup=self.get_keyboard())

        @self.router.message(F.text.lower().in_(["детально", "так"]))
        async def confirm_detail(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)

            if not st["pending_detail_q"]:
                st["detail_next"] = True
                await message.answer("Ок. Напиши питання — відповім детально.", reply_markup=self.get_keyboard())
                return

            q = st["pending_detail_q"]
            st["pending_detail_q"] = None
            st["detail_next"] = True
            async with self.user_locks[user_id]:
                await self.handle_question(message, q)

        @self.router.message()
        async def ai_chat(message: Message):
            text = (message.text or "").strip()
            if not text or text.startswith("/"):
                return

            user_id = message.from_user.id
            async with self.user_locks[user_id]:
                await self.handle_question(message, text)

    async def handle_question(self, message: Message, text: str):
        user_id = message.from_user.id
        st = self.state(user_id)

        do_detail = st["detail_next"]
        st["detail_next"] = False

        if do_detail:
            max_tokens = DETAIL_MAX_TOKENS
            max_chars = DETAIL_MAX_CHARS
            length_rule = "Відповідай детально, але короткими блоками. Максимум 20 рядків."
        else:
            max_tokens = SHORT_MAX_TOKENS
            max_chars = SHORT_MAX_CHARS
            length_rule = (
                "Відповідай коротко: 5–10 рядків.\n"
                "Якщо коротко не можна без втрати сенсу — напиши рівно так:\n"
                "Потрібно детально: <1 причина>"
            )

        prompt = (
            "Пиши по-людськи. Без занудства. Без моралей.\n"
            "Без емодзі.\n"
            "Не тяни сторонні теми, якщо їх не питали.\n"
            "Markdown можна, але акуратно (списки, короткі підзаголовки).\n"
            f"{length_rule}\n\n"
            f"Запит користувача: {text}"
        )

        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

        response = await asyncio.to_thread(
            self.client.ask,
            prompt,
            max_tokens,
            0.4 if not do_detail else 0.35
        )

        # Якщо модель просить деталізацію — не пишемо роман, а питаємо дозвіл
        if (not do_detail) and isinstance(response, str) and response.startswith("Потрібно детально:"):
            st["pending_detail_q"] = text
            msg = response.strip() + "\n\nНаписати детально? Напиши: детально"
            await send_markdown_safe(message.bot, message.chat.id, msg, reply_markup=self.get_keyboard())
            return

        # Авто-стиск якщо вилізло за ліміт (для короткого режиму)
        if (not do_detail) and isinstance(response, str) and len(response) > SHORT_MAX_CHARS:
            compress_prompt = (
                f"Стисни відповідь до {SHORT_MAX_CHARS} символів.\n"
                "Без вступів, без води, без нових фактів.\n"
                "Markdown дозволено.\n\n"
                f"Текст:\n{response}"
            )
            response = await asyncio.to_thread(self.client.ask, compress_prompt, SHORT_MAX_TOKENS, 0.3)

        if do_detail and isinstance(response, str) and len(response) > DETAIL_MAX_CHARS:
            response = response[:DETAIL_MAX_CHARS].rstrip()

        # Відправка з розбиттям
        for chunk in split_chunks(response, 4000):
            await send_markdown_safe(message.bot, message.chat.id, chunk, reply_markup=self.get_keyboard())

    async def start_polling(self):
        print("Телеграм бот запущено!")
        await self.dp.start_polling(self.bot)

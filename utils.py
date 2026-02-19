import asyncio
import re
from aiogram.types import Message
from aiogram.enums import ParseMode
from config import LOADING_FRAMES, LOADING_ICON

async def loading_animation(message: Message, text="Завантаження"):
    try:
        msg = await message.answer(f"{LOADING_ICON} {text}...")
        for _ in range(2):
            for frame in LOADING_FRAMES:
                await asyncio.sleep(0.2)
                try:
                    await msg.edit_text(f"{frame} {text}...")
                except:
                    pass
        await asyncio.sleep(0.1)
        try:
            await msg.delete()
        except:
            pass
    except:
        pass

def split_chunks(text: str, size: int = 3900):
    text = text or ""
    for i in range(0, len(text), size):
        yield text[i:i + size]

async def safe_send(message: Message, text: str, reply_markup=None, parse_mode=None):
    """Безпечна відправка з підтримкою маркдауну"""
    try:
        if parse_mode:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await message.answer(text, reply_markup=reply_markup)
    except Exception as e:
        try:
            # Якщо маркдаун падає - відправляємо без нього
            plain_text = re.sub(r'[*_`\\[\\]()~>#+=|{}.!-]', '', text)
            await message.answer(plain_text[:4000], reply_markup=reply_markup)
        except:
            await message.answer("❌ Помилка відправки", reply_markup=reply_markup)
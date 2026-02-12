import asyncio
from aiogram.types import Message
from config import LOADING_FRAMES, LOADING_ICON

async def loading_animation(message: Message, text="Завантаження"):
    msg = await message.answer(f"{LOADING_ICON} {text}...")
    for _ in range(2):
        for frame in LOADING_FRAMES:
            await asyncio.sleep(0.3)
            try:
                await msg.edit_text(f"{frame} {text}...")
            except:
                pass
    await asyncio.sleep(0.2)
    try:
        await msg.delete()
    except:
        pass
    return msg

def split_chunks(text: str, size: int = 3900):
    text = text or ""
    for i in range(0, len(text), size):
        yield text[i:i + size]
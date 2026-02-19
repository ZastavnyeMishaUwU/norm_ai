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

def escape_markdown(text: str) -> str:
    """Екранує спеціальні символи для Telegram Markdown"""
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def format_ai_response(text: str) -> str:
    """Форматує відповідь AI для красивого виведення"""
    if not text:
        return ""
    
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        if line.startswith('# '):
            formatted_lines.append(f"*{line[2:]}*")
        elif line.startswith('## '):
            formatted_lines.append(f"*{line[3:]}*")
        elif line.startswith('### '):
            formatted_lines.append(f"*{line[4:]}*")
        elif line.startswith('- ') or line.startswith('* '):
            formatted_lines.append(f"• {line[2:]}")
        elif re.match(r'^\d+\. ', line):
            parts = line.split('. ', 1)
            if len(parts) == 2:
                formatted_lines.append(f"{parts[0]}\\. {parts[1]}")
            else:
                formatted_lines.append(line)
        elif '**' in line:
            formatted_lines.append(line.replace('**', '*'))
        else:
            formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)

async def safe_send(message: Message, text: str, reply_markup=None, parse_mode=None):
    """Безпечна відправка з підтримкою маркдауну"""
    try:
        if parse_mode:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await message.answer(text, reply_markup=reply_markup)
    except Exception as e:
        try:
            clean_text = re.sub(r'[*_`\\[\\]()~>#+=|{}.!-]', '', text)
            await message.answer(clean_text[:4000], reply_markup=reply_markup)
        except:
            await message.answer("❌ Помилка відправки", reply_markup=reply_markup)
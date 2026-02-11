import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

MAX_LEN = 3900
SHORT_MAX_TOKENS = 420
DETAIL_MAX_TOKENS = 900
SHORT_MAX_CHARS = 900
DETAIL_MAX_CHARS = 2200

ADMINS_FILE = 'admins.json'
SCHEDULE_FILE = 'school_schedule.json'

def split_chunks(text: str, size: int = MAX_LEN):
    text = text or ""
    for i in range(0, len(text), size):
        yield text[i:i + size]

def normalize_bold(md: str) -> str:
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
    plain = re.sub(r"[*_`]", "", text)
    await bot.send_message(
        chat_id=chat_id,
        text=plain,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )

async def delete_password_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"Не вдалося видалити повідомлення: {e}")

class TelegramBot:
    def __init__(self, client, token: str):
        self.client = client
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()
        
        self.user_locks = defaultdict(asyncio.Lock)
        self.user_state = {}
        
        self.schedule_data = self.load_schedule()
        self.admins_data = self.load_admins()
        
        self.setup_handlers()
        self.dp.include_router(self.router)

    def load_schedule(self):
        try:
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"Завантажено розклад: {len(data.get('classes', []))} класів")
                return data
        except FileNotFoundError:
            print(f"Файл {SCHEDULE_FILE} не знайдено!")
            return {"classes": [], "schedule": {}}
        except json.JSONDecodeError as e:
            print(f"Помилка читання JSON: {e}")
            return {"classes": [], "schedule": {}}

    def load_admins(self):
        try:
            with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "current_password" not in data:
                    data["current_password"] = "admin123"
                    self.save_admins(data)
                return data
        except FileNotFoundError:
            default_admins = {
                "admins": [1259974225],
                "admin_passwords": {},
                "current_password": "admin123"
            }
            self.save_admins(default_admins)
            return default_admins
        except json.JSONDecodeError:
            print("Помилка читання admins.json, створюємо новий")
            default_admins = {
                "admins": [1259974225],
                "admin_passwords": {},
                "current_password": "admin123"
            }
            self.save_admins(default_admins)
            return default_admins

    def save_admins(self, admins_data):
        with open(ADMINS_FILE, 'w', encoding='utf-8') as f:
            json.dump(admins_data, f, ensure_ascii=False, indent=2)

    def state(self, user_id: int):
        if user_id not in self.user_state:
            self.user_state[user_id] = {
                "mode": "assistant",
                "detail_next": False,
                "pending_detail_q": None,
                "current_menu": "main",
                "selected_class": None,
                "selected_day": None,
                "is_admin": user_id in self.admins_data["admins"],
                "awaiting_password": False,
                "awaiting_admin_id": False,
                "awaiting_new_password": False
            }
        return self.user_state[user_id]

    def main_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="AI Помічник"), KeyboardButton(text="Розклад 12 ліцею")],
                [KeyboardButton(text="Адмін-панель")],
            ],
            resize_keyboard=True,
        )

    def ai_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Асистент"), KeyboardButton(text="Програміст")],
                [KeyboardButton(text="Детально (1 раз)"), KeyboardButton(text="Режими")],
                [KeyboardButton(text="Очистити"), KeyboardButton(text="Назад")],
            ],
            resize_keyboard=True,
        )

    def schedule_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Вибрати клас"), KeyboardButton(text="Вибрати день")],
                [KeyboardButton(text="Показати розклад"), KeyboardButton(text="Весь розклад")],
                [KeyboardButton(text="Назад")],
            ],
            resize_keyboard=True,
        )

    def admin_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Статистика"), KeyboardButton(text="Додати адміна")],
                [KeyboardButton(text="Видалити адміна"), KeyboardButton(text="Змінити пароль")],
                [KeyboardButton(text="Список адмінів"), KeyboardButton(text="Оновити розклад")],
                [KeyboardButton(text="Головне меню")],
            ],
            resize_keyboard=True,
        )

    async def classes_inline_keyboard(self):
        builder = InlineKeyboardBuilder()
        classes = self.schedule_data.get('classes', [])
        
        if not classes:
            return None
        
        for class_name in classes:
            builder.button(text=class_name, callback_data=f"class_{class_name}")
        
        builder.button(text="Назад", callback_data="back_to_schedule")
        builder.adjust(3)
        return builder.as_markup()

    async def days_inline_keyboard(self):
        builder = InlineKeyboardBuilder()
        days = {
            "Понеділок": "monday",
            "Вівторок": "tuesday", 
            "Середа": "wednesday",
            "Четвер": "thursday",
            "П'ятниця": "friday"
        }
        
        for day_name, day_key in days.items():
            builder.button(text=day_name, callback_data=f"day_{day_key}")
        
        builder.button(text="Назад", callback_data="back_to_schedule")
        builder.adjust(2)
        return builder.as_markup()

    def get_schedule_for_class_day(self, class_name, day_key):
        if not self.schedule_data or 'schedule' not in self.schedule_data:
            return "Розклад не знайдено"
        
        schedule_day = self.schedule_data['schedule'].get(day_key, [])
        if not schedule_day:
            days_map = {
                'monday': 'Понеділок',
                'tuesday': 'Вівторок',
                'wednesday': 'Середа',
                'thursday': 'Четвер',
                'friday': "П'ятниця"
            }
            day_name = days_map.get(day_key, day_key)
            return f"На {day_name} розкладу немає"
        
        days_map = {
            'monday': 'Понеділок',
            'tuesday': 'Вівторок',
            'wednesday': 'Середа',
            'thursday': 'Четвер',
            'friday': "П'ятниця"
        }
        
        result = f"Розклад для {class_name} ({days_map.get(day_key, day_key)}):\n\n"
        
        for lesson in schedule_day:
            lesson_num = lesson.get('lesson_number', '?')
            class_info = lesson.get('classes', {}).get(class_name, {})
            
            if class_info and class_info.get('subject'):
                subject = class_info['subject']
                room = class_info.get('room', '')
                room_str = f" (каб. {room})" if room else ""
                result += f"{lesson_num}. {subject}{room_str}\n"
            else:
                result += f"{lesson_num}. ---\n"
        
        return result

    def get_full_schedule_for_class(self, class_name):
        if not self.schedule_data or 'schedule' not in self.schedule_data:
            return "Розклад не знайдено"
        
        result = f"Повний розклад для {class_name}:\n\n"
        
        days_ua = {
            'monday': 'Понеділок',
            'tuesday': 'Вівторок',
            'wednesday': 'Середа',
            'thursday': 'Четвер',
            'friday': "П'ятниця"
        }
        
        for day_key, day_name in days_ua.items():
            result += f"**{day_name}:**\n"
            schedule_day = self.schedule_data['schedule'].get(day_key, [])
            
            if schedule_day:
                for lesson in schedule_day:
                    lesson_num = lesson.get('lesson_number', '?')
                    class_info = lesson.get('classes', {}).get(class_name, {})
                    
                    if class_info and class_info.get('subject'):
                        subject = class_info['subject']
                        room = class_info.get('room', '')
                        room_str = f" (каб. {room})" if room else ""
                        result += f"  {lesson_num}. {subject}{room_str}\n"
                    else:
                        result += f"  {lesson_num}. ---\n"
            else:
                result += "  Немає уроків\n"
            
            result += "\n"
        
        return result

    def setup_handlers(self):
        @self.router.message(Command("start"))
        async def start_cmd(message: Message):
            st = self.state(message.from_user.id)
            st.update({
                "mode": "assistant",
                "detail_next": False,
                "pending_detail_q": None,
                "current_menu": "main",
                "selected_class": None,
                "selected_day": None,
                "is_admin": message.from_user.id in self.admins_data["admins"]
            })
            
            welcome_text = (
                "Вітаю! Я бот для 12-го ліцею.\n\n"
                "Доступні опції:\n"
                "• AI Помічник - розумний помічник з різними режимами\n"
                "• Розклад 12 ліцею - перегляд шкільного розкладу\n"
                "• Адмін-панель - керування ботом (тільки для адмінів)\n\n"
                "Оберіть опцію з меню"
            )
            
            await message.answer(welcome_text, reply_markup=self.main_keyboard())

        @self.router.message(F.text == "Назад")
        async def back_to_main(message: Message):
            st = self.state(message.from_user.id)
            st["current_menu"] = "main"
            await message.answer("Головне меню:", reply_markup=self.main_keyboard())

        @self.router.message(F.text == "Головне меню")
        async def back_to_main_from_admin(message: Message):
            st = self.state(message.from_user.id)
            st["current_menu"] = "main"
            await message.answer("Головне меню:", reply_markup=self.main_keyboard())

        @self.router.message(F.text == "AI Помічник")
        async def ai_assistant(message: Message):
            st = self.state(message.from_user.id)
            st["current_menu"] = "ai"
            await message.answer(
                "Режим AI Помічника\n\n"
                "Доступні команди:\n"
                "• Асистент - звичайний режим\n"
                "• Програміст - технічні питання\n"
                "• Детально (1 раз) - детальна відповідь\n"
                "• Режими - список доступних режимів\n"
                "• Очистити - скинути контекст\n"
                "• Назад - повернутися назад",
                reply_markup=self.ai_keyboard()
            )

        @self.router.message(F.text == "Асистент")
        async def assistant_mode(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "ai":
                st["mode"] = "assistant"
                await message.answer("Режим: Асистент", reply_markup=self.ai_keyboard())

        @self.router.message(F.text == "Програміст")
        async def programmer_mode(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "ai":
                st["mode"] = "teach"
                await message.answer("Режим: Програміст", reply_markup=self.ai_keyboard())

        @self.router.message(F.text == "Детально (1 раз)")
        async def detail_once(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "ai":
                st["detail_next"] = True
                await message.answer("Наступна відповідь буде детально", reply_markup=self.ai_keyboard())

        @self.router.message(F.text == "Очистити")
        async def clear_state(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "ai":
                st.update({
                    "detail_next": False,
                    "pending_detail_q": None
                })
                await message.answer("Контекст очищено", reply_markup=self.ai_keyboard())

        @self.router.message(F.text == "Режими")
        async def modes_cmd(message: Message):
            modes = self.client.get_available_modes()
            if not modes:
                await message.answer("Режимів немає. (Створіть папку instructions/ з .txt файлами)")
                return
            await message.answer("Доступні режими:\n" + "\n".join(f"• {m}" for m in modes))

        @self.router.message(F.text == "Розклад 12 ліцею")
        async def schedule_menu(message: Message):
            st = self.state(message.from_user.id)
            st["current_menu"] = "schedule"
            
            if not self.schedule_data or not self.schedule_data.get('classes'):
                await message.answer("Розклад не завантажено. Зверніться до адміністратора.", reply_markup=self.schedule_keyboard())
                return
            
            selected_info = ""
            if st["selected_class"]:
                selected_info += f"Клас: {st['selected_class']}\n"
            if st["selected_day"]:
                days_map = {
                    'monday': 'Понеділок',
                    'tuesday': 'Вівторок',
                    'wednesday': 'Середа',
                    'thursday': 'Четвер',
                    'friday': "П'ятниця"
                }
                selected_info += f"День: {days_map.get(st['selected_day'], st['selected_day'])}\n"
            
            info_text = "Меню розкладу\n\n" + (f"Обрано:\n{selected_info}" if selected_info else "Нічого не обрано\n")
            info_text += "\nОберіть опцію:"
            
            await message.answer(info_text, reply_markup=self.schedule_keyboard())

        @self.router.message(F.text == "Вибрати клас")
        async def select_class_menu(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "schedule":
                keyboard = await self.classes_inline_keyboard()
                if not keyboard:
                    await message.answer("Список класів не знайдено. Можливо, розклад не завантажено.", reply_markup=self.schedule_keyboard())
                    return
                await message.answer("Оберіть клас:", reply_markup=keyboard)

        @self.router.message(F.text == "Вибрати день")
        async def select_day_menu(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "schedule":
                if not st["selected_class"]:
                    await message.answer("Спочатку оберіть клас!", reply_markup=self.schedule_keyboard())
                    return
                
                keyboard = await self.days_inline_keyboard()
                await message.answer("Оберіть день тижня:", reply_markup=keyboard)

        @self.router.message(F.text == "Показати розклад")
        async def show_schedule(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "schedule":
                if not st["selected_class"]:
                    await message.answer("Спочатку оберіть клас!", reply_markup=self.schedule_keyboard())
                    return
                if not st["selected_day"]:
                    await message.answer("Спочатку оберіть день!", reply_markup=self.schedule_keyboard())
                    return
                
                schedule_text = self.get_schedule_for_class_day(st["selected_class"], st["selected_day"])
                await message.answer(schedule_text, reply_markup=self.schedule_keyboard())

        @self.router.message(F.text == "Весь розклад")
        async def show_full_schedule(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "schedule":
                if not st["selected_class"]:
                    await message.answer("Спочатку оберіть клас!", reply_markup=self.schedule_keyboard())
                    return
                
                schedule_text = self.get_full_schedule_for_class(st["selected_class"])
                if len(schedule_text) > 4000:
                    parts = list(split_chunks(schedule_text, 4000))
                    for i, part in enumerate(parts):
                        await message.answer(part, parse_mode=ParseMode.MARKDOWN if i == 0 else None, reply_markup=self.schedule_keyboard())
                else:
                    await message.answer(schedule_text, parse_mode=ParseMode.MARKDOWN, reply_markup=self.schedule_keyboard())

        @self.router.callback_query(F.data.startswith("class_"))
        async def handle_class_selection(callback: CallbackQuery):
            class_name = callback.data.split("_", 1)[1]
            user_id = callback.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "schedule":
                st["selected_class"] = class_name
                st["selected_day"] = None  # Скидаємо день при зміні класу
                try:
                    await callback.message.edit_text(f"Обрано клас: {class_name}")
                except:
                    pass  # Якщо не вдалося редагувати, продовжуємо
                await callback.answer(f"Клас {class_name} обрано")
                await callback.message.answer(f"Клас {class_name} обрано. Тепер оберіть день.", reply_markup=self.schedule_keyboard())

        @self.router.callback_query(F.data.startswith("day_"))
        async def handle_day_selection(callback: CallbackQuery):
            day_key = callback.data.split("_", 1)[1]
            user_id = callback.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "schedule":
                if not st["selected_class"]:
                    await callback.answer("Спочатку оберіть клас!")
                    return
                
                days_map = {
                    'monday': 'Понеділок',
                    'tuesday': 'Вівторок',
                    'wednesday': 'Середа',
                    'thursday': 'Четвер',
                    'friday': "П'ятниця"
                }
                day_name = days_map.get(day_key, day_key)
                st["selected_day"] = day_key
                try:
                    await callback.message.edit_text(f"Обрано день: {day_name}")
                except:
                    pass
                await callback.answer(f"День {day_name} обрано")
                await callback.message.answer(f"День {day_name} обрано. Тепер можете подивитись розклад.", reply_markup=self.schedule_keyboard())

        @self.router.callback_query(F.data == "back_to_schedule")
        async def back_to_schedule_menu(callback: CallbackQuery):
            try:
                await callback.message.delete()
            except:
                pass
            await callback.message.answer("Повертаємося до меню розкладу...", reply_markup=self.schedule_keyboard())
            await callback.answer()

        @self.router.message(F.text == "Адмін-панель")
        async def admin_panel(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["is_admin"]:
                st["current_menu"] = "admin"
                await message.answer(
                    "Адмін-панель\n\n"
                    "Доступні команди:\n"
                    "• Статистика - інформація про бота\n"
                    "• Додати адміна - додати нового адміністратора\n"
                    "• Видалити адміна - видалити адміністратора\n"
                    "• Змінити пароль - змінити пароль для адмінів\n"
                    "• Список адмінів - перегляд всіх адмінів\n"
                    "• Оновити розклад - перезавантажити розклад\n"
                    "• Головне меню - повернутися назад",
                    reply_markup=self.admin_keyboard()
                )
            else:
                st["awaiting_password"] = True
                await message.answer(
                    "Адмін-авторизація\n\n"
                    "Введіть пароль для доступу до адмін-панелі:\n"
                    f"(Поточний пароль: {self.admins_data['current_password']})",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="Скасувати")]],
                        resize_keyboard=True
                    )
                )

        @self.router.message(F.text == "Скасувати")
        async def cancel_auth(message: Message):
            st = self.state(message.from_user.id)
            st.update({
                "awaiting_password": False,
                "awaiting_admin_id": False,
                "awaiting_new_password": False
            })
            await message.answer("Скасовано", reply_markup=self.main_keyboard())

        @self.router.message(lambda message: self.state(message.from_user.id)["awaiting_password"])
        async def handle_password_input(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st["awaiting_password"]:
                return
            
            await delete_password_message(self.bot, message.chat.id, message.message_id)
            
            if message.text == self.admins_data["current_password"]:
                st["is_admin"] = True
                st["awaiting_password"] = False
                
                if user_id not in self.admins_data["admins"]:
                    self.admins_data["admins"].append(user_id)
                    self.save_admins(self.admins_data)
                
                if str(user_id) not in self.admins_data["admin_passwords"]:
                    self.admins_data["admin_passwords"][str(user_id)] = message.text
                    self.save_admins(self.admins_data)
                
                st["current_menu"] = "admin"
                await message.answer(
                    "Авторизація успішна!\n\n"
                    "Тепер ви маєте доступ до адмін-панелі.",
                    reply_markup=self.admin_keyboard()
                )
            else:
                await message.answer(
                    "Невірний пароль!\n\n"
                    "Спробуйте ще раз або скасуйте:",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="Скасувати")]],
                        resize_keyboard=True
                    )
                )

        @self.router.message(F.text == "Статистика")
        async def admin_stats(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "admin" and st["is_admin"]:
                classes_count = len(self.schedule_data.get('classes', [])) if self.schedule_data else 0
                days_count = len(self.schedule_data.get('schedule', {})) if self.schedule_data else 0
                
                stats_text = (
                    f"Статистика бота:\n"
                    f"• Користувачів: {len(self.user_state)}\n"
                    f"• Адміністраторів: {len(self.admins_data['admins'])}\n"
                    f"• Класів у розкладі: {classes_count}\n"
                    f"• Днів у розкладі: {days_count}\n"
                    f"• Час сервера: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"• Поточний пароль: {self.admins_data['current_password']}"
                )
                await message.answer(stats_text)

        @self.router.message(F.text == "Додати адміна")
        async def add_admin(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "admin" and st["is_admin"]:
                st["awaiting_admin_id"] = True
                await message.answer(
                    "Введіть ID користувача Telegram, якого хочете додати як адміністратора:\n"
                    "(ID можна отримати через бота @userinfobot)\n\n"
                    "Формат: тільки цифри",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="Скасувати")]],
                        resize_keyboard=True
                    )
                )

        @self.router.message(lambda message: self.state(message.from_user.id)["awaiting_admin_id"])
        async def handle_admin_id_input(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st["awaiting_admin_id"]:
                return
            
            text = message.text.strip()
            if text == "Скасувати":
                st["awaiting_admin_id"] = False
                await message.answer("Скасовано", reply_markup=self.admin_keyboard())
                return
            
            try:
                new_admin_id = int(text)
                if new_admin_id in self.admins_data["admins"]:
                    await message.answer(f"Користувач з ID {new_admin_id} вже є адміністратором.")
                else:
                    self.admins_data["admins"].append(new_admin_id)
                    self.save_admins(self.admins_data)
                    await message.answer(f"Користувач з ID {new_admin_id} доданий як адміністратор!")
            except ValueError:
                await message.answer("Некоректний ID. Введіть тільки цифри.")
            
            st["awaiting_admin_id"] = False
            await message.answer("Що робитимемо далі?", reply_markup=self.admin_keyboard())

        @self.router.message(F.text == "Видалити адміна")
        async def remove_admin(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "admin" and st["is_admin"]:
                if len(self.admins_data["admins"]) <= 1:
                    await message.answer("Не можна видалити останнього адміністратора!")
                    return
                
                admins_list = "\n".join([f"• {admin_id}" for admin_id in self.admins_data["admins"]])
                await message.answer(
                    f"Список адміністраторів:\n{admins_list}\n\n"
                    "Введіть ID адміністратора для видалення:",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="Скасувати")]],
                        resize_keyboard=True
                    )
                )
                st["awaiting_admin_id"] = True

        @self.router.message(F.text == "Змінити пароль")
        async def change_password(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "admin" and st["is_admin"]:
                st["awaiting_new_password"] = True
                await message.answer(
                    "Введіть новий пароль для адмін-панелі:\n"
                    f"(Поточний пароль: {self.admins_data['current_password']})",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="Скасувати")]],
                        resize_keyboard=True
                    )
                )

        @self.router.message(lambda message: self.state(message.from_user.id)["awaiting_new_password"])
        async def handle_new_password(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st["awaiting_new_password"]:
                return
            
            text = message.text.strip()
            if text == "Скасувати":
                st["awaiting_new_password"] = False
                await message.answer("Скасовано", reply_markup=self.admin_keyboard())
                return
            
            if len(text) < 4:
                await message.answer("Пароль повинен містити щонайменше 4 символи!")
                return
            
            old_password = self.admins_data["current_password"]
            self.admins_data["current_password"] = text
            self.save_admins(self.admins_data)
            
            st["awaiting_new_password"] = False
            await message.answer(
                f"Пароль успішно змінено!\n"
                f"Старий пароль: {old_password}\n"
                f"Новий пароль: {text}",
                reply_markup=self.admin_keyboard()
            )

        @self.router.message(F.text == "Список адмінів")
        async def list_admins(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "admin" and st["is_admin"]:
                admins_list = "\n".join([f"• {admin_id}" for admin_id in self.admins_data["admins"]])
                passwords_info = "\n".join([f"• {uid}: {pwd}" for uid, pwd in self.admins_data.get("admin_passwords", {}).items()])
                
                response = f"Список адміністраторів:\n{admins_list}\n\n"
                if passwords_info:
                    response += f"Історія паролів:\n{passwords_info}\n\n"
                response += f"Поточний пароль: {self.admins_data['current_password']}"
                
                await message.answer(response)

        @self.router.message(F.text == "Оновити розклад")
        async def reload_schedule(message: Message):
            st = self.state(message.from_user.id)
            if st["current_menu"] == "admin" and st["is_admin"]:
                self.schedule_data = self.load_schedule()
                if self.schedule_data and self.schedule_data.get('classes'):
                    await message.answer(
                        f"Розклад успішно оновлено!\n"
                        f"• Завантажено класів: {len(self.schedule_data.get('classes', []))}\n"
                        f"• Завантажено днів: {len(self.schedule_data.get('schedule', {}))}",
                        reply_markup=self.admin_keyboard()
                    )
                else:
                    await message.answer("Не вдалося завантажити розклад!", reply_markup=self.admin_keyboard())

        @self.router.message()
        async def ai_chat(message: Message):
            text = (message.text or "").strip()
            if not text or text.startswith("/"):
                return
            
            st = self.state(message.from_user.id)
            
            if st["current_menu"] == "ai":
                user_id = message.from_user.id
                async with self.user_locks[user_id]:
                    await self.handle_ai_question(message, text)
            elif st["current_menu"] == "main":
                await message.answer("Оберіть опцію з меню", reply_markup=self.main_keyboard())

    async def handle_ai_question(self, message: Message, text: str):
        user_id = message.from_user.id
        st = self.state(user_id)
        
        mode = st["mode"]
        do_detail = st["detail_next"]
        st["detail_next"] = False

        if do_detail:
            max_tokens = DETAIL_MAX_TOKENS
            max_chars = DETAIL_MAX_CHARS
            length_rule = "Відповідь детально, але без води. Максимум 20 рядків."
        else:
            max_tokens = SHORT_MAX_TOKENS
            max_chars = SHORT_MAX_CHARS
            length_rule = (
                "Відповідь коротко: 5–10 рядків.\n"
                "Якщо коротко не можна без втрати сенсу — напиши рівно так:\n"
                "Потрібно детально: <1 причина>"
            )

        prompt = (
            "Пиши по-людськи. Без занудства. Без моралей.\n"
            "Без емодзі.\n"
            "Не тягни сторонні теми, якщо їх не питали.\n"
            "Markdown можна, але акуратно.\n"
            f"{length_rule}\n\n"
            f"Запит: {text}"
        )

        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        response = await asyncio.to_thread(
            self.client.ask,
            prompt,
            mode,
            max_tokens,
            0.4 if not do_detail else 0.35,
        )

        if (not do_detail) and isinstance(response, str) and response.startswith("Потрібно детально:"):
            st["pending_detail_q"] = text
            msg = response.strip() + "\n\nНаписати детально? Напиши: детально"
            await send_markdown_safe(message.bot, message.chat.id, msg, reply_markup=self.ai_keyboard())
            return

        if (not do_detail) and isinstance(response, str) and len(response) > max_chars:
            compress_prompt = (
                f"Стисни відповідь до {max_chars} символів.\n"
                "Без вступів, без води, без нових фактів.\n"
                "Markdown дозволено.\n\n"
                f"Текст:\n{response}"
            )
            response = await asyncio.to_thread(self.client.ask, compress_prompt, mode, SHORT_MAX_TOKENS, 0.3)

        if do_detail and isinstance(response, str) and len(response) > DETAIL_MAX_CHARS:
            response = response[:DETAIL_MAX_CHARS].rstrip()

        for chunk in split_chunks(response, 4000):
            await send_markdown_safe(message.bot, message.chat.id, chunk, reply_markup=self.ai_keyboard())

    async def start_polling(self):
        print("Бот запущено")
        await self.dp.start_polling(self.bot)
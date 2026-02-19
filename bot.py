import asyncio
import json
from collections import defaultdict
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import *
from utils import loading_animation, split_chunks, safe_send
from geminiclient import GeminiClient

class TelegramBot:
    def __init__(self, client, token: str):
        self.client = client
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()
        
        self.user_locks = defaultdict(asyncio.Lock)
        self.user_state = {}
        
        self.schedule_data = self.load_json(SCHEDULE_FILE, {"classes": ALL_CLASSES, "schedule": {}})
        self.bells_data = self.load_json(BELLS_FILE, {"shift_1": {}, "shift_2": {}})
        self.admins_data = self.load_json(ADMINS_FILE, {"admins": [1259974225], "current_password": "admin123", "donors": []})
        self.donors = set(self.admins_data.get("donors", []))
        self.stats = STATS
        
        self.setup_handlers()
        self.dp.include_router(self.router)

    def load_json(self, filename, default):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default

    def is_donor(self, user_id: int):
        return user_id in self.donors

    def state(self, user_id: int):
        if user_id not in self.user_state:
            is_admin = user_id in self.admins_data.get("admins", [])
            is_donor = self.is_donor(user_id)
            
            self.user_state[user_id] = {
                "mode": "assistant",
                "detail_next": False,
                "current_menu": "main",
                "selected_class": None,
                "selected_day": None,
                "is_admin": is_admin,
                "is_donor": is_donor,
                "awaiting_password": False,
                "awaiting_broadcast": False,
                "awaiting_new_password": False,
                "awaiting_mode_name": False,
                "awaiting_mode_instruction": False,
                "temp_mode_name": None,
                "first_seen": datetime.now(),
                "last_active": datetime.now()
            }
            
            self.stats.total_users += 1
            self.stats.daily_active.add(user_id)
        
        self.user_state[user_id]["last_active"] = datetime.now()
        self.stats.online_users.add(user_id)
        self.stats.daily_active.add(user_id)
        self.stats.active_today = len(self.stats.daily_active)
        
        return self.user_state[user_id]

    def get_schedule_for_class_day(self, class_name, day_key):
        if not class_name or not day_key:
            return "❌ Помилка: не вибрано клас або день"
        
        schedule_day = self.schedule_data.get('schedule', {}).get(day_key, [])
        if not schedule_day:
            day_name = DAYS_UA_REVERSE.get(day_key, day_key)
            return f"📭 На {day_name} розкладу немає"
        
        day_name = DAYS_UA_REVERSE.get(day_key, day_key)
        
        result = f"{SCHEDULE_ICON} {class_name} — {day_name}\n\n"
        
        found = False
        for lesson in schedule_day:
            lesson_num = lesson.get('lesson_number')
            class_info = lesson.get('classes', {}).get(class_name, {})
            
            if class_info and class_info.get('subject'):
                subject = class_info['subject']
                room = class_info.get('room', '')
                room_str = f" (каб. {room})" if room else ""
                result += f"{lesson_num}. {subject}{room_str}\n"
                found = True
        
        if not found:
            result += "Немає уроків\n"
        
        return result

    def get_full_schedule_for_class(self, class_name):
        if not class_name:
            return "❌ Помилка: не вибрано клас"
        
        result = f"{SCHEDULE_ICON} Повний розклад — {class_name}\n\n"
        
        for day_key, day_name in DAYS_UA.items():
            result += f"——— {day_name} ———\n"
            schedule_day = self.schedule_data.get('schedule', {}).get(day_key, [])
            
            found = False
            for lesson in schedule_day:
                lesson_num = lesson.get('lesson_number')
                class_info = lesson.get('classes', {}).get(class_name, {})
                
                if class_info and class_info.get('subject'):
                    subject = class_info['subject']
                    room = class_info.get('room', '')
                    room_str = f" (каб. {room})" if room else ""
                    result += f"  {lesson_num}. {subject}{room_str}\n"
                    found = True
            
            if not found:
                result += "  Немає уроків\n"
            result += "\n"
        
        return result

    def get_schedule_for_today(self, class_name):
        today = datetime.now().weekday()
        days_map = {0: "monday", 1: "tuesday", 2: "wednesday", 
                   3: "thursday", 4: "friday", 5: "monday", 6: "monday"}
        day_key = days_map[today]
        day_name = DAYS_UA_REVERSE.get(day_key, "")
        schedule = self.get_schedule_for_class_day(class_name, day_key)
        return schedule.replace(f"{day_name}", f"СЬОГОДНІ ({day_name})")

    def get_schedule_for_tomorrow(self, class_name):
        tomorrow = (datetime.now().weekday() + 1) % 7
        days_map = {0: "monday", 1: "tuesday", 2: "wednesday", 
                   3: "thursday", 4: "friday", 5: "monday", 6: "monday"}
        day_key = days_map[tomorrow]
        day_name = DAYS_UA_REVERSE.get(day_key, "")
        schedule = self.get_schedule_for_class_day(class_name, day_key)
        return schedule.replace(f"{day_name}", f"ЗАВТРА ({day_name})")

    def main_keyboard(self, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        
        keyboard = [
            [KeyboardButton(text=f"{AI_ICON} AI Помічник"), 
             KeyboardButton(text=f"{SCHEDULE_ICON} Розклад")]
        ]
        
        row2 = [KeyboardButton(text=f"{BELL_ICON} Дзвінки")]
        if show_donate:
            row2.append(KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        keyboard.append(row2)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    def ai_keyboard(self, user_id=None):
        modes = self.client.get_available_modes()
        keyboard = []
        row = []
        for i, mode in enumerate(modes, 1):
            row.append(KeyboardButton(text=mode))
            if i % 2 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([KeyboardButton(text="Детально"), KeyboardButton(text="Очистити")])
        keyboard.append([KeyboardButton(text=f"{BACK_ICON} Назад"), 
                        KeyboardButton(text=f"{MENU_ICON} Головне меню")])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    def schedule_main_keyboard(self, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        
        keyboard = [
            [KeyboardButton(text=f"{CLASS_ICON} Вибрати клас")],
            [KeyboardButton(text="📆 Сьогодні"), KeyboardButton(text="📅 Завтра")],
            [KeyboardButton(text=f"{BELL_ICON} Дзвінки")]
        ]
        
        row4 = [KeyboardButton(text=f"{BACK_ICON} Назад"), 
                KeyboardButton(text=f"{MENU_ICON} Головне меню")]
        if show_donate:
            row4.insert(0, KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        keyboard.append(row4)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def classes_keyboard(self, user_id=None):
    classes = ALL_CLASSES
    print(f"📚 Завантажено класів з ALL_CLASSES: {len(classes)}")
    print(f"📋 Список класів: {classes}")
    
    st = self.state(user_id) if user_id else None
    show_donate = st and not st.get("is_donor", False)
    
    keyboard = []
    row = []
    
    # Правильне сортування класів
    sorted_classes = sorted(classes, key=lambda x: (int(x.split('-')[0]), x))
    print(f"📋 Відсортовані класи: {sorted_classes}")
    
    for i, class_name in enumerate(sorted_classes, 1):
        row.append(KeyboardButton(text=f"{CLASS_ICON}{class_name}"))
        if i % 4 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    row_last = [KeyboardButton(text=f"{BACK_ICON} Назад")]
    if show_donate:
        row_last.insert(0, KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
    keyboard.append(row_last)
    
    print(f"✅ Створено клавіатуру з {len(sorted_classes)} класами")
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    def days_keyboard(self, class_name, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        
        keyboard = [
            [KeyboardButton(text=f"{DAY_ICON} Понеділок"), 
             KeyboardButton(text=f"{DAY_ICON} Вівторок")],
            [KeyboardButton(text=f"{DAY_ICON} Середа"), 
             KeyboardButton(text=f"{DAY_ICON} Четвер")],
            [KeyboardButton(text=f"{DAY_ICON} П'ятниця")]
        ]
        
        row3 = [KeyboardButton(text=f"{BACK_ICON} Інший клас"), 
                KeyboardButton(text=f"{BACK_ICON} Назад")]
        if show_donate:
            row3.insert(0, KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        keyboard.append(row3)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    def schedule_result_keyboard(self, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        
        keyboard = [
            [KeyboardButton(text="📆 Сьогодні"), 
             KeyboardButton(text="📅 Завтра")],
            [KeyboardButton(text=f"{BACK_ICON} Інший день"), 
             KeyboardButton(text=f"{BACK_ICON} Інший клас")],
            [KeyboardButton(text="📋 Весь розклад"), 
             KeyboardButton(text=f"{BELL_ICON} Дзвінки")]
        ]
        
        row4 = [KeyboardButton(text=f"{BACK_ICON} Назад"), 
                KeyboardButton(text=f"{MENU_ICON} Головне меню")]
        if show_donate:
            row4.insert(0, KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        keyboard.append(row4)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    def admin_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📊 Статистика")],
                [KeyboardButton(text="🔑 Змінити пароль")],
                [KeyboardButton(text="📢 Розсилка"), 
                 KeyboardButton(text="👥 Активні")],
                [KeyboardButton(text="🤖 Керування режимами AI")],
                [KeyboardButton(text=f"{BACK_ICON} Назад"), 
                 KeyboardButton(text=f"{MENU_ICON} Головне меню")]
            ],
            resize_keyboard=True
        )

    def ai_management_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📋 Список режимів")],
                [KeyboardButton(text="➕ Додати новий режим")],
                [KeyboardButton(text="❌ Видалити режим")],
                [KeyboardButton(text=f"{BACK_ICON} Назад до адмінки")]
            ],
            resize_keyboard=True
        )

    def bells_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🇦 І зміна"), KeyboardButton(text="🇧 ІІ зміна")],
                [KeyboardButton(text=f"{BACK_ICON} Назад"), 
                 KeyboardButton(text=f"{MENU_ICON} Головне меню")]
            ],
            resize_keyboard=True
        )

    def bells_result_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=f"{BELL_ICON} Інша зміна")],
                [KeyboardButton(text=f"{BACK_ICON} Назад"), 
                 KeyboardButton(text=f"{MENU_ICON} Головне меню")]
            ],
            resize_keyboard=True
        )

    def cancel_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Скасувати")]],
            resize_keyboard=True
        )

    def donate_keyboard(self):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"{DONATE_ICON} Підтримати", url=MONOBANK_URL)],
                [InlineKeyboardButton(text="✅ Я задонатив", callback_data="donate_done")]
            ]
        )

    def setup_handlers(self):
        
        @self.router.message(Command("start"))
        async def start_cmd(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            st.update({
                "mode": "assistant",
                "detail_next": False,
                "current_menu": "main",
                "selected_class": None,
                "selected_day": None
            })
            
            self.stats.commands_used += 1
            
            welcome_text = (
                f"{MENU_ICON} Вітаю в боті 12-го ліцею!\n\n"
                f"{AI_ICON} AI Помічник - різні режими\n"
                f"{SCHEDULE_ICON} Розклад - 5-11 класи\n"
                f"{BELL_ICON} Дзвінки - І та ІІ зміна\n"
                f"{DONATE_ICON} Підтримати проект\n\n"
                f"Оберіть опцію в меню:"
            )
            
            if st.get("is_admin"):
                welcome_text += f"\n\n{ADMIN_ICON} Ви адмін. Використовуйте /admin"
            
            if st.get("is_donor"):
                welcome_text += f"\n\n{DONOR_ICON} Дякуємо за підтримку!"
            
            await safe_send(message, welcome_text, self.main_keyboard(user_id))

        @self.router.message(Command("admin"))
        async def admin_cmd(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["is_admin"]:
                st["current_menu"] = "admin"
                await safe_send(
                    message,
                    f"{ADMIN_ICON} Адмін-панель\n\n"
                    f"📊 Статистика\n"
                    f"🔑 Змінити пароль\n"
                    f"📢 Розсилка\n"
                    f"👥 Активні\n"
                    f"🤖 Керування режимами AI",
                    self.admin_keyboard()
                )
            else:
                st["awaiting_password"] = True
                await safe_send(message, f"{ADMIN_ICON} Введіть пароль:", self.cancel_keyboard())

        @self.router.message(F.text == "❌ Скасувати")
        async def cancel_action(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st.update({
                "awaiting_password": False,
                "awaiting_broadcast": False,
                "awaiting_new_password": False,
                "awaiting_mode_name": False,
                "awaiting_mode_instruction": False,
                "temp_mode_name": None
            })
            await safe_send(message, f"{MENU_ICON} Скасовано", self.main_keyboard(user_id))

        @self.router.message(lambda m: self.state(m.from_user.id)["awaiting_password"])
        async def handle_password(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            try:
                await self.bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            if message.text == self.admins_data["current_password"]:
                st["is_admin"] = True
                st["awaiting_password"] = False
                if user_id not in self.admins_data["admins"]:
                    self.admins_data["admins"].append(user_id)
                st["current_menu"] = "admin"
                await safe_send(message, f"{ADMIN_ICON} Успішно!", self.admin_keyboard())
            else:
                await safe_send(message, "❌ Невірний пароль", self.cancel_keyboard())

        @self.router.message(F.text == f"{MENU_ICON} Головне меню")
        async def back_to_main(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st.update({"current_menu": "main", "selected_class": None, "selected_day": None})
            await safe_send(message, f"{MENU_ICON} Головне меню", self.main_keyboard(user_id))

        @self.router.message(F.text == f"{BACK_ICON} Назад")
        async def back_button(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "schedule":
                st["selected_class"] = None
                st["selected_day"] = None
                await safe_send(message, f"{SCHEDULE_ICON} Розклад", self.schedule_main_keyboard(user_id))
            elif st["current_menu"] == "ai":
                st["selected_class"] = None
                st["selected_day"] = None
                await safe_send(message, f"{AI_ICON} AI Помічник", self.ai_keyboard(user_id))
            elif st["current_menu"] == "admin":
                await safe_send(message, f"{ADMIN_ICON} Адмін-панель", self.admin_keyboard())
            elif st["current_menu"] == "ai_management":
                st["current_menu"] = "admin"
                await safe_send(message, f"{ADMIN_ICON} Адмін-панель", self.admin_keyboard())
            else:
                await safe_send(message, f"{MENU_ICON} Головне меню", self.main_keyboard(user_id))

        @self.router.message(F.text == f"{BACK_ICON} Інший клас")
        async def other_class(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["selected_class"] = None
            st["selected_day"] = None
            await safe_send(message, "Оберіть клас:", self.classes_keyboard(user_id))

        @self.router.message(F.text == f"{BACK_ICON} Інший день")
        async def other_day(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st.get("selected_class"):
                await safe_send(message, "❌ Спочатку оберіть клас!", self.classes_keyboard(user_id))
                return
            
            st["selected_day"] = None
            await safe_send(
                message,
                f"{SCHEDULE_ICON} Клас: {st['selected_class']}\n\nОберіть день:",
                self.days_keyboard(st['selected_class'], user_id)
            )

        @self.router.message(F.text == "🔙 Назад до адмінки")
        async def back_to_admin(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["current_menu"] = "admin"
            await safe_send(message, f"{ADMIN_ICON} Адмін-панель", self.admin_keyboard())

        @self.router.message(F.text.contains(f"{DONATE_ICON} Підтримати"))
        async def donate_cmd(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st.get("is_donor"):
                await safe_send(message, f"{DONOR_ICON} Ви вже підтримали!", self.main_keyboard(user_id))
                return
            
            await message.answer(
                f"{DONATE_ICON} Підтримати проект\n\n"
                f"1. Перейдіть за посиланням\n"
                f"2. Зробіть донат від 50 грн\n"
                f"3. В описі вкажіть ID: {user_id}\n"
                f"4. Натисніть «Я задонатив»",
                reply_markup=self.donate_keyboard()
            )

        @self.router.callback_query(F.data == "donate_done")
        async def donate_done(callback: CallbackQuery):
            user_id = callback.from_user.id
            st = self.state(user_id)
            
            st["is_donor"] = True
            self.donors.add(user_id)
            self.stats.donors.add(user_id)
            
            await callback.message.edit_text(f"{DONATE_ICON} Дякуємо! Адмін перевірить платіж.")
            await callback.answer()

        @self.router.message(F.text.contains(f"{BELL_ICON} Дзвінки"))
        async def bells_menu(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            await safe_send(
                message,
                f"{BELL_ICON} *Розклад дзвінків*\n\nОберіть зміну:",
                self.bells_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )

        @self.router.message(F.text.in_(["🇦 І зміна", "🇧 ІІ зміна"]))
        async def show_bells(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            shift = 1 if message.text == "🇦 І зміна" else 2
            
            await loading_animation(message, "Завантаження")
            
            if shift == 1:
                bells_text = (
                    f"{BELL_ICON} *І зміна*\n\n"
                    f"*1*\\. 08:00–08:35\n"
                    f"   └ перерва 10 хв\n"
                    f"*2*\\. 08:45–09:20\n"
                    f"   └ перерва 10 хв\n"
                    f"*3*\\. 09:30–10:05\n"
                    f"   └ перерва 10 хв\n"
                    f"*4*\\. 10:15–10:50\n"
                    f"   └ перерва 10 хв\n"
                    f"*5*\\. 11:00–11:35\n"
                    f"   └ перерва 15 хв\n"
                    f"*6*\\. 11:50–12:25\n"
                    f"   └ перерва 10 хв\n"
                    f"*7*\\. 12:35–13:10\n"
                    f"   └ перерва 15 хв"
                )
            else:
                bells_text = (
                    f"{BELL_ICON} *ІІ зміна*\n\n"
                    f"*0*\\. 12:35–13:10 (підготовчий)\n"
                    f"   └ перерва 15 хв\n"
                    f"*1*\\. 13:25–14:00\n"
                    f"   └ перерва 10 хв\n"
                    f"*2*\\. 14:10–14:45\n"
                    f"   └ перерва 10 хв\n"
                    f"*3*\\. 14:55–15:30\n"
                    f"   └ перерва 10 хв\n"
                    f"*4*\\. 15:40–16:15\n"
                    f"   └ перерва 5 хв\n"
                    f"*5*\\. 16:20–16:55\n"
                    f"   └ перерва 5 хв\n"
                    f"*6*\\. 17:00–17:35"
                )
            
            await message.answer(bells_text, reply_markup=self.bells_result_keyboard(), parse_mode=ParseMode.MARKDOWN)

        @self.router.message(F.text == f"{BELL_ICON} Інша зміна")
        async def other_bells(message: Message):
            await safe_send(
                message,
                f"{BELL_ICON} *Розклад дзвінків*\n\nОберіть зміну:",
                self.bells_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )

        @self.router.message(F.text.contains(f"{AI_ICON} AI Помічник"))
        async def ai_assistant(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["current_menu"] = "ai"
            self.stats.commands_used += 1
            
            await safe_send(
                message,
                f"{AI_ICON} AI Помічник\n\nОберіть режим:",
                self.ai_keyboard(user_id)
            )

        @self.router.message(lambda m: m.text in self.client.get_available_modes())
        async def select_mode(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["mode"] = message.text
            await safe_send(message, f"✅ Режим: {message.text}", self.ai_keyboard(user_id))

        @self.router.message(F.text == "Детально")
        async def detail_mode(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["detail_next"] = True
            await safe_send(message, "✅ Наступна відповідь буде детальною", self.ai_keyboard(user_id))

        @self.router.message(F.text == "Очистити")
        async def clear_mode(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["detail_next"] = False
            await safe_send(message, "🧹 Контекст очищено", self.ai_keyboard(user_id))

        @self.router.message(F.text.contains(f"{SCHEDULE_ICON} Розклад"))
        async def schedule_start(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["current_menu"] = "schedule"
            self.stats.commands_used += 1
            self.stats.schedule_views += 1
            
            if st.get("selected_class"):
                await safe_send(
                    message,
                    f"{SCHEDULE_ICON} Розклад\n\nОбраний клас: {st['selected_class']}\n\nОберіть день:",
                    self.days_keyboard(st['selected_class'], user_id)
                )
            else:
                await safe_send(message, f"{SCHEDULE_ICON} Розклад\n\nОберіть опцію:", self.schedule_main_keyboard(user_id))

        @self.router.message(F.text == f"{CLASS_ICON} Вибрати клас")
        async def select_class_menu(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "schedule":
                await safe_send(message, "Оберіть клас:", self.classes_keyboard(user_id))

        @self.router.message(lambda m: m.text and m.text.startswith(CLASS_ICON))
        async def select_class(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            class_name = message.text.replace(CLASS_ICON, "").strip()
            st["selected_class"] = class_name
            st["selected_day"] = None
            
            await safe_send(
                message,
                f"{SCHEDULE_ICON} Обрано клас: {class_name}\n\nОберіть день:",
                self.days_keyboard(class_name, user_id)
            )

        @self.router.message(lambda m: m.text and m.text.startswith(DAY_ICON))
        async def select_day(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st.get("selected_class"):
                await safe_send(message, "❌ Спочатку оберіть клас!", self.classes_keyboard(user_id))
                return
            
            day_name = message.text.replace(DAY_ICON, "").strip()
            day_key = DAYS_UA.get(day_name)
            
            if not day_key:
                return
            
            st["selected_day"] = day_key
            self.stats.schedule_views += 1
            
            await loading_animation(message, "Завантаження")
            schedule_text = self.get_schedule_for_class_day(st["selected_class"], day_key)
            
            await safe_send(message, schedule_text, self.schedule_result_keyboard(user_id))

        @self.router.message(F.text == "📆 Сьогодні")
        async def schedule_today(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st.get("selected_class"):
                await safe_send(message, "❌ Спочатку оберіть клас!", self.classes_keyboard(user_id))
                return
            
            await loading_animation(message, "Завантаження")
            schedule_text = self.get_schedule_for_today(st["selected_class"])
            await safe_send(message, schedule_text, self.schedule_result_keyboard(user_id))

        @self.router.message(F.text == "📅 Завтра")
        async def schedule_tomorrow(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st.get("selected_class"):
                await safe_send(message, "❌ Спочатку оберіть клас!", self.classes_keyboard(user_id))
                return
            
            await loading_animation(message, "Завантаження")
            schedule_text = self.get_schedule_for_tomorrow(st["selected_class"])
            await safe_send(message, schedule_text, self.schedule_result_keyboard(user_id))

        @self.router.message(F.text == "📋 Весь розклад")
        async def full_schedule(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if not st.get("selected_class"):
                await safe_send(message, "❌ Спочатку оберіть клас!", self.classes_keyboard(user_id))
                return
            
            await loading_animation(message, "Завантаження")
            schedule_text = self.get_full_schedule_for_class(st["selected_class"])
            
            if len(schedule_text) > 4000:
                for chunk in split_chunks(schedule_text, 4000):
                    await safe_send(message, chunk, self.schedule_result_keyboard(user_id))
            else:
                await safe_send(message, schedule_text, self.schedule_result_keyboard(user_id))

        @self.router.message(F.text == "📊 Статистика")
        async def admin_stats(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                online_now = len(self.stats.online_users)
                active_today = len(self.stats.daily_active)
                total_users = self.stats.total_users
                commands = self.stats.commands_used
                schedule_views = self.stats.schedule_views
                ai_queries = self.stats.ai_queries
                uptime = datetime.now() - self.stats.start_time
                hours = int(uptime.total_seconds() // 3600)
                minutes = int((uptime.total_seconds() % 3600) // 60)
                
                await safe_send(
                    message,
                    f"{ADMIN_ICON} Статистика\n\n"
                    f"🟢 Онлайн зараз: {online_now}\n"
                    f"📅 Активні сьогодні: {active_today}\n"
                    f"👥 Всього: {total_users}\n"
                    f"📊 Команд: {commands}\n"
                    f"📋 Розклад: {schedule_views}\n"
                    f"🤖 AI: {ai_queries}\n"
                    f"⏱ Аптайм: {hours} год {minutes} хв\n"
                    f"💰 Донатерів: {len(self.donors)}"
                )

        @self.router.message(F.text == "👥 Активні")
        async def admin_active(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                online_list = list(self.stats.online_users)[:20]
                online_text = "\n".join([f"• {uid}" for uid in online_list]) if online_list else "• Немає активних"
                
                await safe_send(
                    message,
                    f"👥 Активні користувачі\n\n"
                    f"🟢 Зараз: {len(self.stats.online_users)}\n"
                    f"{online_text}\n\n"
                    f"📅 Сьогодні: {len(self.stats.daily_active)}\n"
                    f"👤 Всього: {self.stats.total_users}"
                )

        @self.router.message(F.text == "🔑 Змінити пароль")
        async def change_password_start(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                st["awaiting_new_password"] = True
                await safe_send(
                    message,
                    f"🔑 Зміна пароля\n\nПоточний пароль: {self.admins_data['current_password']}\n\nВведіть новий пароль:",
                    self.cancel_keyboard()
                )

        @self.router.message(lambda m: self.state(m.from_user.id)["awaiting_new_password"])
        async def change_password_finish(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            try:
                await self.bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            new_pass = message.text.strip()
            if len(new_pass) < 4:
                await safe_send(message, "❌ Пароль має бути від 4 символів!", self.cancel_keyboard())
                return
            
            old = self.admins_data["current_password"]
            self.admins_data["current_password"] = new_pass
            
            try:
                with open(ADMINS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.admins_data, f, ensure_ascii=False, indent=2)
            except:
                pass
            
            st["awaiting_new_password"] = False
            await safe_send(message, f"✅ Пароль змінено!\nСтарий: {old}\nНовий: {new_pass}", self.admin_keyboard())

        @self.router.message(F.text == "📢 Розсилка")
        async def broadcast_start(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                st["awaiting_broadcast"] = True
                await safe_send(message, "📢 Розсилка\n\nВведіть текст для розсилки:", self.cancel_keyboard())

        @self.router.message(lambda m: self.state(m.from_user.id)["awaiting_broadcast"])
        async def broadcast_send(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            text = message.text.strip()
            st["awaiting_broadcast"] = False
            
            await safe_send(message, f"📤 Розсилка запущена...")
            
            sent = 0
            failed = 0
            
            for uid in self.user_state.keys():
                try:
                    await self.bot.send_message(uid, f"📢 {text}")
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    failed += 1
            
            await safe_send(message, f"✅ Розсилка завершена!\n\nВідправлено: {sent}\nПомилок: {failed}", self.admin_keyboard())

        @self.router.message(F.text == "🤖 Керування режимами AI")
        async def ai_management(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                st["current_menu"] = "ai_management"
                await safe_send(
                    message,
                    f"{AI_ICON} Керування режимами AI\n\n"
                    f"📋 Список режимів\n"
                    f"➕ Додати новий режим\n"
                    f"❌ Видалити режим\n\n"
                    f"Режими живуть до перезапуску Render",
                    self.ai_management_keyboard()
                )

        @self.router.message(F.text == "📋 Список режимів")
        async def list_modes_admin(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "ai_management" and st["is_admin"]:
                modes = self.client.get_available_modes()
                text = f"{AI_ICON} Доступні режими:\n\n"
                for mode in modes:
                    if mode in ["assistant", "programmer"]:
                        text += f"• {mode} (базовий)\n"
                    else:
                        text += f"• {mode}\n"
                await safe_send(message, text)

        @self.router.message(F.text == "➕ Додати новий режим")
        async def add_mode_start(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "ai_management" and st["is_admin"]:
                st["awaiting_mode_name"] = True
                await safe_send(
                    message,
                    f"{AI_ICON} Додавання нового режиму\n\n"
                    f"Введіть назву режиму (наприклад: math, history, physics):\n"
                    f"Тільки латиниця, без пробілів",
                    self.cancel_keyboard()
                )

        @self.router.message(lambda m: self.state(m.from_user.id)["awaiting_mode_name"])
        async def add_mode_get_name(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            mode_name = message.text.strip().lower()
            
            if not mode_name or " " in mode_name or not mode_name.isascii():
                await safe_send(message, "❌ Некоректна назва. Тільки латиниця, без пробілів.", self.cancel_keyboard())
                st["awaiting_mode_name"] = False
                return
            
            existing = self.client.get_available_modes()
            if mode_name in existing:
                await safe_send(message, f"❌ Режим '{mode_name}' вже існує!", self.cancel_keyboard())
                st["awaiting_mode_name"] = False
                return
            
            st["temp_mode_name"] = mode_name
            st["awaiting_mode_name"] = False
            st["awaiting_mode_instruction"] = True
            
            await safe_send(
                message,
                f"✅ Назва: {mode_name}\n\n"
                f"Тепер введіть інструкцію для цього режиму:\n"
                f"Наприклад: Ти професор математики, пояснюй складні формули просто",
                self.cancel_keyboard()
            )

        @self.router.message(lambda m: self.state(m.from_user.id)["awaiting_mode_instruction"])
        async def add_mode_get_instruction(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            instruction = message.text.strip()
            mode_name = st["temp_mode_name"]
            
            if not instruction:
                await safe_send(message, "❌ Інструкція не може бути порожньою!", self.cancel_keyboard())
                return
            
            try:
                await self.bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            status_msg = await message.answer(f"{LOADING_ICON} Додаю режим...")
            
            success = self.client.add_mode(mode_name, instruction)
            
            if success:
                await status_msg.edit_text(
                    f"✅ Режим '{mode_name}' успішно додано!\n\n"
                    f"Інструкція: {instruction[:100]}...\n\n"
                    f"Режим буде доступний до наступного перезапуску Render"
                )
            else:
                await status_msg.edit_text("❌ Помилка при додаванні режиму")
            
            st["awaiting_mode_instruction"] = False
            st["temp_mode_name"] = None

        @self.router.message(F.text == "❌ Видалити режим")
        async def delete_mode_prompt(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "ai_management" and st["is_admin"]:
                modes = self.client.get_available_modes()
                
                keyboard = []
                for mode in modes:
                    if mode not in ["assistant", "programmer"]:
                        keyboard.append([InlineKeyboardButton(text=mode, callback_data=f"del_{mode}")])
                keyboard.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")])
                
                await message.answer("Виберіть режим для видалення:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

        @self.router.callback_query(F.data.startswith("del_"))
        async def delete_mode_confirm(callback: CallbackQuery):
            user_id = callback.from_user.id
            st = self.state(user_id)
            
            if not st["is_admin"]:
                await callback.answer("Немає доступу")
                return
            
            mode = callback.data.replace("del_", "")
            
            if self.client.delete_mode(mode):
                await callback.message.edit_text(f"✅ Режим '{mode}' видалено")
            else:
                await callback.message.edit_text(f"❌ Помилка при видаленні")
            
            await callback.answer()

        @self.router.callback_query(F.data == "cancel")
        async def cancel_callback(callback: CallbackQuery):
            await callback.message.delete()
            await callback.answer()

        @self.router.message()
        async def ai_chat(message: Message):
            text = (message.text or "").strip()
            if not text or text.startswith("/"):
                return
            
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "ai":
                self.stats.ai_queries += 1
                self.stats.commands_used += 1
                
                async with self.user_locks[user_id]:
                    await self.handle_ai_question(message, text, st["mode"])

    async def handle_ai_question(self, message: Message, text: str, mode: str):
        st = self.state(message.from_user.id)
        do_detail = st["detail_next"]
        st["detail_next"] = False

        if do_detail:
            max_tokens = DETAIL_MAX_TOKENS
            length_rule = "Відповідь детально, розгорнуто. Використовуй заголовки, списки, жирний текст."
        else:
            max_tokens = SHORT_MAX_TOKENS
            length_rule = "Відповідь коротко, по суті. Використовуй списки для ключових пунктів."

        prompt = f"{length_rule}\n\nЗапит: {text}"

        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        try:
            response = await asyncio.to_thread(
                self.client.ask,
                prompt,
                mode,
                max_tokens,
                0.4 if not do_detail else 0.35,
            )
        except Exception as e:
            response = f"❌ Помилка: {str(e)[:100]}"

        if response and len(response) > 4000:
            for chunk in split_chunks(response, 4000):
                await safe_send(message, chunk, self.ai_keyboard(message.from_user.id), parse_mode=ParseMode.MARKDOWN)
        else:
            await safe_send(message, response or "❌ Немає відповіді", self.ai_keyboard(message.from_user.id), parse_mode=ParseMode.MARKDOWN)

    async def drop_pending_updates(self):
        try:
            await self.bot.delete_webhook(drop_pending_updates=True)
        except:
            pass

    async def start_polling(self):
        print("✅ Бот запущено")
        print(f"👑 Адмінів: {len(self.admins_data.get('admins', []))}")
        print(f"💰 Донатерів: {len(self.donors)}")
        print(f"🤖 Режимів: {len(self.client.get_available_modes())}")
        print(f"📚 Класів: {len(ALL_CLASSES)}")
        
        await self.drop_pending_updates()
        await self.dp.start_polling(self.bot, drop_pending_updates=True)
import asyncio
import json
from collections import defaultdict
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import *
from parser import ScheduleParser
from utils import loading_animation, split_chunks
from geminiclient import GeminiClient

class TelegramBot:
    def __init__(self, client, token: str):
        self.client = client
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()
        
        self.user_locks = defaultdict(asyncio.Lock)
        self.user_state = {}
        
        self.parser = ScheduleParser()
        self.admins_data = self.load_admins()
        self.donors = set(self.admins_data.get("donors", []))
        self.stats = STATS
        
        self.setup_handlers()
        self.dp.include_router(self.router)
    
    def load_admins(self):
        try:
            with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {
                "admins": [1259974225],
                "current_password": "admin123",
                "donors": []
            }
    
    def is_donor(self, user_id: int):
        return user_id in self.donors or user_id in self.stats.donors
    
    def state(self, user_id: int):
        if user_id not in self.user_state:
            is_admin = user_id in self.admins_data.get("admins", [])
            is_donor = self.is_donor(user_id)
            
            self.user_state[user_id] = {
                "mode": "assistant",
                "detail_next": False,
                "pending_detail_q": None,
                "current_menu": "main",
                "selected_class": None,
                "selected_day": None,
                "selected_shift": None,
                "is_admin": is_admin,
                "is_donor": is_donor,
                "awaiting_password": False,
                "awaiting_broadcast": False,
                "donate_clicked": False,
                "first_seen": datetime.now(),
                "last_active": datetime.now(),
                "donate_hidden": is_donor
            }
            
            self.stats.total_users += 1
            self.stats.daily_active.add(user_id)
        
        self.user_state[user_id]["last_active"] = datetime.now()
        self.stats.online_users.add(user_id)
        self.stats.daily_active.add(user_id)
        self.stats.active_today = len(self.stats.daily_active)
        
        return self.user_state[user_id]
    
    def main_keyboard(self, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False) and not st.get("donate_hidden", False)
        
        keyboard = [
            [KeyboardButton(text=f"{AI_ICON} AI Помічник"), 
             KeyboardButton(text=f"{SCHEDULE_ICON} Розклад")]
        ]
        
        row2 = []
        if show_donate:
            row2.append(KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        row2.append(KeyboardButton(text=f"{BELL_ICON} Дзвінки"))
        keyboard.append(row2)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    def ai_keyboard(self, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        
        keyboard = [
            [KeyboardButton(text="Асистент"), KeyboardButton(text="Програміст")],
            [KeyboardButton(text="Детально (1 раз)"), KeyboardButton(text="Режими")],
            [KeyboardButton(text="Очистити")]
        ]
        
        row3 = []
        if show_donate:
            row3.append(KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        row3.append(KeyboardButton(text=f"{MENU_ICON} Головне меню"))
        keyboard.append(row3)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    def schedule_main_keyboard(self, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        
        keyboard = [
            [KeyboardButton(text=f"{CLASS_ICON} Вибрати клас")],
            [KeyboardButton(text="📆 Сьогодні"), KeyboardButton(text="📅 Завтра")],
            [KeyboardButton(text=f"{BELL_ICON} Дзвінки")]
        ]
        
        row4 = []
        if show_donate:
            row4.append(KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        row4.append(KeyboardButton(text=f"{MENU_ICON} Головне меню"))
        keyboard.append(row4)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    def classes_keyboard(self, user_id=None):
        classes = self.parser.get_classes()
        if not classes:
            return None
        
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        
        keyboard = []
        row = []
        
        for i, class_name in enumerate(classes, 1):
            row.append(KeyboardButton(text=f"{CLASS_ICON}{class_name}"))
            if i % 4 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        row_last = []
        if show_donate:
            row_last.append(KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        row_last.append(KeyboardButton(text=f"{BACK_ICON} Назад"))
        keyboard.append(row_last)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    def days_keyboard(self, class_name, user_id=None):
        st = self.state(user_id) if user_id else None
        show_donate = st and not st.get("is_donor", False)
        shift = self.parser.get_shift_for_class(class_name)
        
        keyboard = [
            [KeyboardButton(text=f"{DAY_ICON} Понеділок"), 
             KeyboardButton(text=f"{DAY_ICON} Вівторок")],
            [KeyboardButton(text=f"{DAY_ICON} Середа"), 
             KeyboardButton(text=f"{DAY_ICON} Четвер")],
            [KeyboardButton(text=f"{DAY_ICON} П'ятниця")]
        ]
        
        row3 = []
        if show_donate:
            row3.append(KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        row3.append(KeyboardButton(text=f"{BACK_ICON} Інший клас"))
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
        
        row4 = []
        if show_donate:
            row4.append(KeyboardButton(text=f"{DONATE_ICON} Підтримати"))
        row4.append(KeyboardButton(text=f"{MENU_ICON} Головне меню"))
        keyboard.append(row4)
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    def admin_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📊 Статистика реального часу")],
                [KeyboardButton(text="🔄 Оновити розклад")],
                [KeyboardButton(text="🔑 Змінити пароль")],
                [KeyboardButton(text="📢 Розсилка"), 
                 KeyboardButton(text="👥 Активні користувачі")],
                [KeyboardButton(text=f"{MENU_ICON} Головне меню")]
            ],
            resize_keyboard=True
        )
    
    def donate_keyboard(self):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"{DONATE_ICON} Підтримати бота (Monobank)", url=MONOBANK_URL)],
                [InlineKeyboardButton(text="✅ Я задонатив", callback_data="donate_done")],
                [InlineKeyboardButton(text="❌ Сховати назавжди", callback_data="donate_hide")]
            ]
        )
        return keyboard
    
    def setup_handlers(self):
        
        @self.router.message(Command("start"))
        async def start_cmd(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            st.update({
                "mode": "assistant",
                "detail_next": False,
                "pending_detail_q": None,
                "current_menu": "main",
                "selected_class": None,
                "selected_day": None
            })
            
            self.stats.commands_used += 1
            
            welcome_text = (
                f"{MENU_ICON} *Вітаю в боті 12-го ліцею!*\n\n"
                f"{AI_ICON} *AI Помічник* — відповіді на питання\n"
                f"{SCHEDULE_ICON} *Розклад* — 1-11 класи, 2 зміни\n"
                f"{BELL_ICON} *Дзвінки* — розклад уроків\n"
                f"{DONATE_ICON} *Підтримка* — допомогти проекту\n\n"
            )
            
            if st.get("is_donor"):
                welcome_text += f"{DONOR_ICON} *Дякуємо за підтримку!*"
            
            await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=self.main_keyboard(user_id))
        
        @self.router.message(Command("admin"))
        async def admin_panel_cmd(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["is_admin"]:
                st["current_menu"] = "admin"
                await message.answer(
                    f"{ADMIN_ICON} *Адмін-панель*\n\n"
                    f"📊 Статистика реального часу\n"
                    f"🔄 Оновити розклад\n"
                    f"🔑 Змінити пароль\n"
                    f"📢 Розсилка\n"
                    f"👥 Активні користувачі\n\n"
                    f"_Адміни додаються тільки через JSON-файл_",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.admin_keyboard()
                )
            else:
                st["awaiting_password"] = True
                await message.answer(
                    f"{ADMIN_ICON} *Авторизація*\n\nВведіть пароль:",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
                        resize_keyboard=True
                    )
                )
        
        @self.router.message(F.text == "❌ Скасувати")
        async def cancel_action(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["awaiting_password"] = False
            st["awaiting_broadcast"] = False
            await message.answer(f"{MENU_ICON} Скасовано", reply_markup=self.main_keyboard(user_id))
        
        @self.router.message(lambda message: self.state(message.from_user.id)["awaiting_password"] and message.text != "❌ Скасувати")
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
                await message.answer(
                    f"{ADMIN_ICON} *Авторизація успішна!*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.admin_keyboard()
                )
            else:
                await message.answer(
                    "❌ *Невірний пароль!*\nСпробуйте ще раз:",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
                        resize_keyboard=True
                    )
                )
        
        @self.router.message(F.text.contains(f"{MENU_ICON} Головне меню"))
        async def back_to_main(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st.update({"current_menu": "main", "selected_class": None, "selected_day": None})
            self.stats.commands_used += 1
            await message.answer(f"{MENU_ICON} *Головне меню*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.main_keyboard(user_id))
        
        @self.router.message(F.text.contains(f"{BACK_ICON} Назад"))
        async def back_button(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "schedule":
                st["selected_class"] = None
                st["selected_day"] = None
                await message.answer("Оберіть опцію:", reply_markup=self.schedule_main_keyboard(user_id))
        
        @self.router.message(F.text.contains(f"{DONATE_ICON} Підтримати"))
        async def donate_cmd(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st.get("is_donor"):
                await message.answer(
                    f"{DONOR_ICON} *Ви вже підтримали проект!*\n\nДякуємо за вашу допомогу! 🙏",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.main_keyboard(user_id)
                )
                return
            
            donate_text = (
                f"{DONATE_ICON} *Підтримати розробку бота*\n\n"
                f"Бот працює безкоштовно 24/7, але сервери та API потребують коштів.\n\n"
                f"*Як допомогти:*\n"
                f"1️⃣ Перейдіть за посиланням на Monobank\n"
                f"2️⃣ Зробіть донат від 50 грн\n"
                f"3️⃣ В описі до платежу вкажіть свій Telegram ID: `{user_id}`\n"
                f"4️⃣ Натисніть *«Я задонатив»*\n\n"
                f"*Після перевірки ви отримаєте:*\n"
                f"⭐ Спеціальний статус\n"
                f"🚫 Зникнуть кнопки донату\n"
                f"🎁 Ексклюзивні фішки\n\n"
                f"*Ваш Telegram ID:* `{user_id}`"
            )
            
            await message.answer(donate_text, parse_mode=ParseMode.MARKDOWN, reply_markup=self.donate_keyboard())
        
        @self.router.callback_query(F.data == "donate_done")
        async def donate_done(callback: CallbackQuery):
            user_id = callback.from_user.id
            
            await callback.message.edit_text(
                f"{DONATE_ICON} *Дякуємо за підтримку!*\n\n"
                f"Адміністратор перевірить платіж і додасть вас до списку донатерів.\n"
                f"Це може зайняти деякий час.\n\n"
                f"Ваш ID: `{user_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
            
            for admin_id in self.admins_data.get("admins", []):
                try:
                    await self.bot.send_message(
                        admin_id,
                        f"{DONATE_ICON} *Новий донат!*\n\n"
                        f"Користувач: {user_id}\n"
                        f"Username: @{callback.from_user.username or 'немає'}\n"
                        f"Додайте в donors.json",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
            
            await callback.answer("Дякуємо!")
        
        @self.router.callback_query(F.data == "donate_hide")
        async def donate_hide(callback: CallbackQuery):
            user_id = callback.from_user.id
            st = self.state(user_id)
            st["donate_hidden"] = True
            
            await callback.message.edit_text(
                f"{MENU_ICON} *Кнопки донату приховано*\n\n"
                f"Ви можете повернути їх у будь-який момент через /start",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
        
        @self.router.message(F.text.contains(f"{BELL_ICON} Дзвінки"))
        async def bells_schedule(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            await loading_animation(message, "Завантаження розкладу дзвінків")
            
            if st.get("selected_class"):
                shift = self.parser.get_shift_for_class(st["selected_class"])
            else:
                hour = datetime.now().hour
                shift = 2 if hour >= 12 else 1
            
            bells_text = self.parser.format_bells_schedule(shift)
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=f"{BACK_ICON} Назад")],
                    [KeyboardButton(text=f"{MENU_ICON} Головне меню")]
                ],
                resize_keyboard=True
            )
            
            await message.answer(bells_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        
        @self.router.message(F.text.contains(f"{AI_ICON} AI Помічник"))
        async def ai_assistant(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["current_menu"] = "ai"
            self.stats.commands_used += 1
            
            await message.answer(
                f"{AI_ICON} *Режим AI Помічника*\n\n"
                f"▸ *Асистент* — загальні питання\n"
                f"▸ *Програміст* — технічні питання\n"
                f"▸ *Детально (1 раз)* — розгорнута відповідь\n"
                f"▸ *Режими* — список усіх режимів\n"
                f"▸ *Очистити* — скинути історію\n\n"
                f"_Просто напишіть ваше питання..._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.ai_keyboard(user_id)
            )
        
        @self.router.message(F.text == "Асистент")
        async def assistant_mode(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "ai":
                st["mode"] = "assistant"
                await message.answer("✅ *Режим: Асистент*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.ai_keyboard(user_id))
        
        @self.router.message(F.text == "Програміст")
        async def programmer_mode(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "ai":
                st["mode"] = "teach"
                await message.answer("✅ *Режим: Програміст*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.ai_keyboard(user_id))
        
        @self.router.message(F.text == "Детально (1 раз)")
        async def detail_once(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "ai":
                st["detail_next"] = True
                await message.answer("✅ *Наступна відповідь буде детальною*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.ai_keyboard(user_id))
        
        @self.router.message(F.text == "Очистити")
        async def clear_state(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "ai":
                st.update({"detail_next": False, "pending_detail_q": None})
                await message.answer("🧹 *Контекст очищено*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.ai_keyboard(user_id))
        
        @self.router.message(F.text == "Режими")
        async def modes_cmd(message: Message):
            modes = self.client.get_available_modes()
            if not modes:
                await message.answer("📭 *Немає додаткових режимів*", parse_mode=ParseMode.MARKDOWN)
                return
            text = "📋 *Доступні режими:*\n\n" + "\n".join(f"▸ {m}" for m in modes)
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.router.message(F.text.contains(f"{SCHEDULE_ICON} Розклад"))
        async def schedule_start(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            st["current_menu"] = "schedule"
            st["selected_class"] = None
            st["selected_day"] = None
            self.stats.commands_used += 1
            self.stats.schedule_views += 1
            
            classes = self.parser.get_classes()
            if not classes:
                await message.answer(
                    "❌ *Розклад не завантажено*\nЗверніться до адміністратора.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.main_keyboard(user_id)
                )
                return
            
            await message.answer(
                f"{SCHEDULE_ICON} *Розклад 12 ліцею*\n\nОберіть опцію:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.schedule_main_keyboard(user_id)
            )
        
        @self.router.message(F.text == f"{CLASS_ICON} Вибрати клас")
        async def select_class_menu(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "schedule":
                keyboard = self.classes_keyboard(user_id)
                if keyboard:
                    await message.answer("Оберіть ваш клас:", reply_markup=keyboard)
        
        @self.router.message(lambda message: message.text and message.text.startswith(CLASS_ICON))
        async def select_class(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] != "schedule":
                return
            
            class_name = message.text.replace(CLASS_ICON, "")
            st["selected_class"] = class_name
            st["selected_day"] = None
            shift = self.parser.get_shift_for_class(class_name)
            shift_text = SHIFTS[str(shift)]
            
            await message.answer(
                f"{SCHEDULE_ICON} *Обрано клас:* {class_name}\n{shift_text}\n\nТепер оберіть день 👇",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.days_keyboard(class_name, user_id)
            )
        
        @self.router.message(lambda message: message.text and message.text.startswith(DAY_ICON))
        async def select_day(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] != "schedule":
                return
            if not st["selected_class"]:
                await message.answer("❌ *Спочатку оберіть клас!*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.classes_keyboard(user_id))
                return
            
            day_name = message.text.replace(DAY_ICON, "")
            day_key = DAYS_UA.get(day_name)
            
            if not day_key:
                return
            
            st["selected_day"] = day_key
            self.stats.schedule_views += 1
            
            await loading_animation(message, "Завантаження розкладу")
            schedule_text = self.parser.get_schedule_for_class_day(st["selected_class"], day_key)
            
            await message.answer(schedule_text, parse_mode=ParseMode.MARKDOWN, reply_markup=self.schedule_result_keyboard(user_id))
        
        @self.router.message(F.text == "📆 Сьогодні")
        async def schedule_today(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] != "schedule":
                return
            if not st["selected_class"]:
                await message.answer("❌ *Спочатку оберіть клас!*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.classes_keyboard(user_id))
                return
            
            await loading_animation(message, "Завантаження розкладу на сьогодні")
            schedule_text = self.parser.get_schedule_for_today(st["selected_class"])
            await message.answer(schedule_text, parse_mode=ParseMode.MARKDOWN, reply_markup=self.schedule_result_keyboard(user_id))
        
        @self.router.message(F.text == "📅 Завтра")
        async def schedule_tomorrow(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] != "schedule":
                return
            if not st["selected_class"]:
                await message.answer("❌ *Спочатку оберіть клас!*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.classes_keyboard(user_id))
                return
            
            await loading_animation(message, "Завантаження розкладу на завтра")
            schedule_text = self.parser.get_schedule_for_tomorrow(st["selected_class"])
            await message.answer(schedule_text, parse_mode=ParseMode.MARKDOWN, reply_markup=self.schedule_result_keyboard(user_id))
        
        @self.router.message(F.text == "📋 Весь розклад")
        async def full_schedule(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] != "schedule":
                return
            if not st["selected_class"]:
                await message.answer("❌ *Спочатку оберіть клас!*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.classes_keyboard(user_id))
                return
            
            await loading_animation(message, "Завантаження повного розкладу")
            schedule_text = self.parser.get_full_schedule_for_class(st["selected_class"])
            
            if len(schedule_text) > 4000:
                parts = list(split_chunks(schedule_text, 4000))
                for i, part in enumerate(parts):
                    await message.answer(
                        part,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=self.schedule_result_keyboard(user_id) if i == len(parts)-1 else None
                    )
            else:
                await message.answer(schedule_text, parse_mode=ParseMode.MARKDOWN, reply_markup=self.schedule_result_keyboard(user_id))
        
        @self.router.message(F.text.contains(f"{BACK_ICON} Інший клас"))
        async def other_class(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "schedule":
                st["selected_class"] = None
                st["selected_day"] = None
                keyboard = self.classes_keyboard(user_id)
                if keyboard:
                    await message.answer("Оберіть інший клас:", reply_markup=keyboard)
        
        @self.router.message(F.text.contains(f"{BACK_ICON} Інший день"))
        async def other_day(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            if st["current_menu"] == "schedule":
                if not st["selected_class"]:
                    await message.answer("❌ *Спочатку оберіть клас!*", parse_mode=ParseMode.MARKDOWN, reply_markup=self.classes_keyboard(user_id))
                    return
                
                st["selected_day"] = None
                await message.answer(
                    f"{SCHEDULE_ICON} *Клас:* {st['selected_class']}\n\nОберіть інший день:",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.days_keyboard(st['selected_class'], user_id)
                )
        
        @self.router.message(F.text == "📊 Статистика реального часу")
        async def admin_stats_realtime(message: Message):
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
                
                stats_text = (
                    f"{ADMIN_ICON} *Статистика в реальному часі*\n\n"
                    f"🟢 *Онлайн зараз:* {online_now}\n"
                    f"📅 *Активні сьогодні:* {active_today}\n"
                    f"👥 *Всього користувачів:* {total_users}\n"
                    f"📊 *Всього команд:* {commands}\n"
                    f"📋 *Переглядів розкладу:* {schedule_views}\n"
                    f"🤖 *AI запитів:* {ai_queries}\n"
                    f"⏱ *Аптайм:* {hours} год {minutes} хв\n"
                    f"💰 *Донатерів:* {len(self.donors) + len(self.stats.donors)}\n\n"
                    f"_Дані в ОЗУ, скидаються при перезапуску_"
                )
                
                await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)
        
        @self.router.message(F.text == "👥 Активні користувачі")
        async def admin_active_users(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                online_list = list(self.stats.online_users)[:20]
                online_text = "\n".join([f"• `{uid}`" for uid in online_list]) if online_list else "• Немає активних"
                
                text = (
                    f"👥 *Активні користувачі*\n\n"
                    f"🟢 *Зараз онлайн:* {len(self.stats.online_users)}\n"
                    f"{online_text}\n\n"
                    f"📅 *Сьогодні:* {len(self.stats.daily_active)}\n"
                    f"👤 *Всього:* {self.stats.total_users}"
                )
                
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.router.message(F.text == "🔄 Оновити розклад")
        async def admin_reload_schedule(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                await loading_animation(message, "Оновлення розкладу")
                self.parser.reload()
                classes_count = len(self.parser.get_classes())
                
                await message.answer(
                    f"✅ *Розклад оновлено!*\n\n📚 Класів: {classes_count}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.admin_keyboard()
                )
        
        @self.router.message(F.text == "🔑 Змінити пароль")
        async def admin_change_password_start(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                st["awaiting_password"] = "change"
                await message.answer(
                    f"🔑 *Зміна пароля*\n\nПоточний пароль: `{self.admins_data['current_password']}`\n\nВведіть *новий пароль*:",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
                        resize_keyboard=True
                    )
                )
        
        @self.router.message(lambda message: self.state(message.from_user.id)["awaiting_password"] == "change" and message.text != "❌ Скасувати")
        async def admin_change_password_finish(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            try:
                await self.bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            new_password = message.text.strip()
            if len(new_password) < 4:
                await message.answer(
                    "❌ *Пароль має бути від 4 символів!*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
                        resize_keyboard=True
                    )
                )
                return
            
            old_password = self.admins_data["current_password"]
            self.admins_data["current_password"] = new_password
            
            try:
                with open(ADMINS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.admins_data, f, ensure_ascii=False, indent=2)
            except:
                pass
            
            st["awaiting_password"] = False
            await message.answer(
                f"✅ *Пароль успішно змінено!*\n\nСтарий: `{old_password}`\nНовий: `{new_password}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.admin_keyboard()
            )
        
        @self.router.message(F.text == "📢 Розсилка")
        async def admin_broadcast_start(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            if st["current_menu"] == "admin" and st["is_admin"]:
                st["awaiting_broadcast"] = True
                await message.answer(
                    "📢 *Розсилка*\n\nВведіть текст для розсилки всім користувачам:",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
                        resize_keyboard=True
                    )
                )
        
        @self.router.message(lambda message: self.state(message.from_user.id)["awaiting_broadcast"] and message.text != "❌ Скасувати")
        async def admin_broadcast_send(message: Message):
            user_id = message.from_user.id
            st = self.state(user_id)
            
            broadcast_text = message.text.strip()
            st["awaiting_broadcast"] = False
            
            await message.answer(f"📤 *Розсилка запущена...*", parse_mode=ParseMode.MARKDOWN)
            
            sent = 0
            failed = 0
            
            for uid in self.user_state.keys():
                try:
                    await self.bot.send_message(
                        uid,
                        f"📢 *Оголошення адміністратора:*\n\n{broadcast_text}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    failed += 1
            
            await message.answer(
                f"✅ *Розсилка завершена!*\n\n"
                f"📨 Відправлено: {sent}\n"
                f"❌ Помилок: {failed}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.admin_keyboard()
            )
        
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
                    await self.handle_ai_question(message, text)
    
    async def handle_ai_question(self, message: Message, text: str):
        user_id = message.from_user.id
        st = self.state(user_id)
        
        mode = st["mode"]
        do_detail = st["detail_next"]
        st["detail_next"] = False

        if do_detail:
            max_tokens = DETAIL_MAX_TOKENS
            length_rule = "Відповідь детально, розгорнуто, але без води. Максимум 20 рядків."
        else:
            max_tokens = SHORT_MAX_TOKENS
            length_rule = "Відповідь коротко: 3-7 рядків, тільки суть."

        prompt = (
            "Ти корисний AI асистент. Пиши по-людськи, природно.\n"
            "Без зайвих вступів, без моралей, без емодзі.\n"
            "Використовуй просту, зрозумілу мову.\n"
            f"{length_rule}\n\n"
            f"Запит: {text}"
        )

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
                await message.answer(chunk, reply_markup=self.ai_keyboard(user_id))
        else:
            await message.answer(response or "❌ Немає відповіді", reply_markup=self.ai_keyboard(user_id))

    async def start_polling(self):
        print(f"✅ Бот 12-го ліцею запущено")
        print(f"📚 Завантажено класів: {len(self.parser.get_classes())}")
        print(f"👑 Адмінів: {len(self.admins_data.get('admins', []))}")
        print(f"💰 Донатерів: {len(self.donors)}")
        await self.dp.start_polling(self.bot)
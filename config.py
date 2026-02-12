import os
from datetime import datetime

MAX_LEN = 3900
SHORT_MAX_TOKENS = 420
DETAIL_MAX_TOKENS = 900
SHORT_MAX_CHARS = 900
DETAIL_MAX_CHARS = 2200

ADMINS_FILE = 'admins.json'
SCHEDULE_FILE = 'school_schedule.json'
ELEMENTARY_SCHEDULE_FILE = 'elementary_schedule.json'
BELLS_FILE = 'bells_schedule.json'

CLASS_ICON = "● "
DAY_ICON = "▶ "
BACK_ICON = "◀ "
MENU_ICON = "■ "
SCHEDULE_ICON = "📋 "
AI_ICON = "🤖 "
ADMIN_ICON = "⚙️ "
DONATE_ICON = "💰 "
BELL_ICON = "⏰ "
LOADING_ICON = "⏳"
DONOR_ICON = "⭐ "

DAYS_UA = {
    "Понеділок": "monday",
    "Вівторок": "tuesday", 
    "Середа": "wednesday",
    "Четвер": "thursday",
    "П'ятниця": "friday"
}

DAYS_UA_REVERSE = {v: k for k, v in DAYS_UA.items()}

SHIFTS = {
    "1": "🇦 І зміна (08:00 - 13:10)",
    "2": "🇧 ІІ зміна (13:25 - 17:35)"
}

SHIFT_1_CLASSES = ["1-А", "1-Б", "1-В", "2-А", "2-Б", "2-В", 
                   "7-А", "7-Б", "7-В", "7-Г", "8-А", "8-Б", "8-В", "8-Г", 
                   "9-А", "9-Б", "9-В", "10-А", "10-Б", "11-А", "11-Б"]

SHIFT_2_CLASSES = ["3-А", "3-Б", "3-В", "4-А", "4-Б", "4-В", 
                   "5-А", "5-Б", "5-В", "6-А", "6-Б", "6-В"]

MONOBANK_URL = "https://send.monobank.ua/jar/96YBXc4K6g"
MONOBANK_LABEL = "Підтримати бот"

LOADING_FRAMES = ["⏳", "⌛", "⏳", "⌛"]

class Stats:
    def __init__(self):
        self.total_users = 0
        self.active_today = 0
        self.commands_used = 0
        self.schedule_views = 0
        self.ai_queries = 0
        self.start_time = datetime.now()
        self.online_users = set()
        self.daily_active = set()
        self.donors = set()

STATS = Stats()
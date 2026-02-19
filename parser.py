import json
from config import SCHEDULE_FILE, ELEMENTARY_SCHEDULE_FILE, BELLS_FILE, SHIFT_1_CLASSES, SHIFT_2_CLASSES, DAYS_UA, DAYS_UA_REVERSE, BELL_ICON, SCHEDULE_ICON, SHIFTS
from datetime import datetime

class ScheduleParser:
    def __init__(self):
        self.main_schedule = self.load_schedule(SCHEDULE_FILE)
        self.elementary_schedule = self.load_schedule(ELEMENTARY_SCHEDULE_FILE)
        self.bells_schedule = self.load_schedule(BELLS_FILE)
        self.merge_schedules()
        self.last_update = datetime.now()
    
    def load_schedule(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"classes": [], "schedule": {}}
    
    def merge_schedules(self):
        if not self.main_schedule:
            self.main_schedule = {"classes": [], "schedule": {}}
        
        elementary_classes = self.elementary_schedule.get('classes', [])
        self.main_schedule['classes'] = list(set(
            self.main_schedule.get('classes', []) + elementary_classes
        ))
        self.main_schedule['classes'] = sorted(
            self.main_schedule['classes'],
            key=lambda x: (int(x.split('-')[0]), x)
        )
        
        for day, lessons in self.elementary_schedule.get('schedule', {}).items():
            if day not in self.main_schedule['schedule']:
                self.main_schedule['schedule'][day] = []
            self.main_schedule['schedule'][day].extend(lessons)
    
    def reload(self):
        self.main_schedule = self.load_schedule(SCHEDULE_FILE)
        self.elementary_schedule = self.load_schedule(ELEMENTARY_SCHEDULE_FILE)
        self.merge_schedules()
        self.last_update = datetime.now()
        return self.main_schedule
    
    def get_classes(self):
        return self.main_schedule.get('classes', [])
    
    def get_shift_for_class(self, class_name):
        if class_name in SHIFT_1_CLASSES:
            return 1
        elif class_name in SHIFT_2_CLASSES:
            return 2
        return 1
    
    def get_bells_schedule(self, shift=1):
        if shift == 1:
            return self.bells_schedule.get('shift_1', {})
        return self.bells_schedule.get('shift_2', {})
    
    def format_bells_schedule(self, shift=1):
        bells = self.get_bells_schedule(shift)
        if not bells or not bells.get('lessons'):
            return f"{BELL_ICON} Розклад дзвінків не знайдено"
        
        shift_name = SHIFTS.get(str(shift), f"{shift} зміна")
        result = f"{BELL_ICON} {shift_name}\n\n"
        
        for lesson in bells.get('lessons', []):
            num = lesson.get('number', '?')
            start = lesson.get('start', '--:--')
            end = lesson.get('end', '--:--')
            break_time = lesson.get('break', 0)
            
            if num == 0:
                result += f"0. {start}–{end} (підготовчий)\n"
            else:
                result += f"{num}. {start}–{end}\n"
            
            if break_time > 0 and num not in [0, 6, 7]:
                result += f"   └ перерва {break_time} хв\n"
        
        return result
    
    def get_schedule_for_class_day(self, class_name, day_key):
        if not class_name or not day_key:
            return "❌ Помилка: не вибрано клас або день"
        
        schedule_day = self.main_schedule.get('schedule', {}).get(day_key, [])
        if not schedule_day:
            day_name = DAYS_UA_REVERSE.get(day_key, day_key)
            return f"📭 На {day_name} розкладу немає"
        
        shift = self.get_shift_for_class(class_name)
        shift_text = f" ({SHIFTS[str(shift)]})" if shift else ""
        day_name = DAYS_UA_REVERSE.get(day_key, day_key)
        
        result = f"{SCHEDULE_ICON} {class_name} — {day_name}{shift_text}\n\n"
        
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
        
        shift = self.get_shift_for_class(class_name)
        shift_text = f" ({SHIFTS[str(shift)]})" if shift else ""
        
        result = f"{SCHEDULE_ICON} Повний розклад — {class_name}{shift_text}\n\n"
        
        for day_key, day_name in DAYS_UA.items():
            result += f"——— {day_name} ———\n"
            schedule_day = self.main_schedule.get('schedule', {}).get(day_key, [])
            
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
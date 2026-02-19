import os
import json
import re
from google import genai

class GeminiClient:
    def __init__(self):
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise RuntimeError("ENV API_KEY is empty")
        self.client = genai.Client(api_key=api_key)
        self.instructions_file = "instructions.json"

    def _load_instructions(self):
        try:
            with open(self.instructions_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            default = {
                "assistant": "Ти корисний універсальний асистент. Відповідай українською мовою. Використовуй форматування: # для заголовків, - для списків, **жирний** для важливого.",
                "programmer": "Ти senior Python developer. Відповідай українською мовою. Використовуй форматування: # для заголовків, - для списків, **жирний** для важливого, `код` для прикладів."
            }
            self._save_instructions(default)
            return default
        except:
            return {}

    def _save_instructions(self, data):
        try:
            with open(self.instructions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except:
            return False

    def get_available_modes(self):
        return list(self._load_instructions().keys())

    def add_mode(self, mode_name: str, instruction: str):
        data = self._load_instructions()
        data[mode_name] = instruction
        return self._save_instructions(data)

    def delete_mode(self, mode_name: str):
        data = self._load_instructions()
        if mode_name in data and mode_name not in ["assistant", "programmer"]:
            del data[mode_name]
            return self._save_instructions(data)
        return False

    def format_response(self, text: str) -> str:
        """Форматує відповідь для красивого виведення"""
        if not text:
            return ""
        
        lines = text.split('\n')
        formatted = []
        
        for line in lines:
            if line.startswith('# '):
                formatted.append(f"*{line[2:]}*")
            elif line.startswith('## '):
                formatted.append(f"*{line[3:]}*")
            elif line.startswith('### '):
                formatted.append(f"*{line[4:]}*")
            elif line.startswith('- '):
                formatted.append(f"• {line[2:]}")
            elif line.startswith('* ') and not line.startswith('**'):
                formatted.append(f"• {line[2:]}")
            elif '**' in line:
                formatted.append(line.replace('**', '*'))
            else:
                formatted.append(line)
        
        return '\n'.join(formatted)

    def ask(self, prompt: str, mode: str = "assistant", max_output_tokens: int = 420, temperature: float = 0.4) -> str:
        try:
            instructions = self._load_instructions()
            system_instruction = instructions.get(mode, instructions.get("assistant", ""))
            
            format_instruction = "\n\nВикористовуй форматування: # заголовки, - списки, **жирний**, `код`."
            system_instruction += format_instruction

            config = {"system_instruction": system_instruction}
            resp = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config,
            )
            
            response = resp.text if getattr(resp, "text", None) else "Порожня відповідь."
            return self.format_response(response)
            
        except Exception as e:
            if "429" in str(e):
                return "Ліміт вичерпано. Почекай і повтори."
            return f"Помилка API: {e}"
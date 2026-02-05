import os
from google import genai


class GeminiClient:
    def __init__(self):
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise RuntimeError("ENV API_KEY is empty")

        self.client = genai.Client(api_key=api_key)
        self.system_instructions = {}
        self.reload_instructions()

    def reload_instructions(self):
        self.system_instructions = {}
        instructions_dir = "instructions"

        if os.path.exists(instructions_dir):
            for filename in os.listdir(instructions_dir):
                if filename.endswith(".txt"):
                    mode_name = filename[:-4]
                    path = os.path.join(instructions_dir, filename)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            self.system_instructions[mode_name] = f.read().strip()
                    except:
                        pass

    def get_available_modes(self):
        return list(self.system_instructions.keys())

    def ask(
        self,
        prompt: str,
        mode: str = "assistant",
        max_output_tokens: int = 420,
        temperature: float = 0.4,
    ) -> str:
        try:
            sys_inst = self.system_instructions.get(mode, "")

            config = {
                "system_instruction": sys_inst,
                "generation_config": {

                    "temperature": 0.7,
                },
            }

            resp = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config,
            )

            return resp.text if getattr(resp, "text", None) else "Порожня відповідь."
        except Exception as e:
            if "429" in str(e):
                return "Ліміт вичерпано. Почекай і повтори."
            return f"Помилка API: {e}"

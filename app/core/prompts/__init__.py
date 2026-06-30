import importlib

class PromptGetter:
    def __init__(self, dbname: str):
        self.my_module = importlib.import_module(f"app.core.prompts.{dbname}")

    def get_prompt(self, prompt_name: str):
        return self.my_module.__getattribute__(prompt_name)
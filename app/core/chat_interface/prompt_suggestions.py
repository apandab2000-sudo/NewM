import yaml
from functools import lru_cache
from app.logger import get_logger


logger = get_logger(__name__)


@lru_cache(maxsize=10)
def load_config(dbname: str):
    with open("app/clientConfig.yaml", "r") as f:
        config = yaml.safe_load(f)
    return config.get(dbname, {}).get("PROMPT_SUGGESTIONS", [])


class PromptSuggestions:
    def __init__(self, dbname: str):
        self.dbname = dbname

    def get(self, use_cache: bool = True):
        return load_config(self.dbname)

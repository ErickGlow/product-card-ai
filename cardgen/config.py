import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

TITLE_MAX = 70
DESC_MIN, DESC_MAX = 800, 1200
QUERIES_MIN, QUERIES_MAX = 3, 5
NO_DATA = "данных нет"


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str
    model: str


def llm_settings() -> LLMSettings:
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Не задан LLM_API_KEY. Скопируйте .env.example в .env и укажите ключ.")
    return LLMSettings(
        api_key=key,
        base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        model=os.environ.get("LLM_MODEL", "openrouter/free"),
    )

"""Загрузка конфигурации из .env"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Bot
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# GLM-5 API
GLM_API_KEY: str = os.getenv("GLM_API_KEY", "")
GLM_API_URL: str = "https://api.z.ai/api/coding/paas/v4/chat/completions"
GLM_MODEL: str = "glm-5"

# Groq Whisper API
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL: str = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL: str = "whisper-large-v3"

# GitHub API
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.getenv("GITHUB_REPO", "sava-repo/new-catalog-2")
GITHUB_API_BASE: str = "https://api.github.com"

# Whitelist (deprecated — доступ управляется через группы)
WHITELIST_CHAT_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("WHITELIST_CHAT_IDS", "").split(",")
    if cid.strip().isdigit()
]

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Instagram cookies (Netscape format, экспорт из браузера — см. COOKIES_GUIDE.md)
INSTAGRAM_COOKIES_FILE: str = os.getenv("INSTAGRAM_COOKIES_FILE", "data/instagram_cookies.txt")

# Database
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "/data/bot.db")

# Limits
MAX_VIDEO_DURATION_SEC: int = 180  # 3 минуты
MIN_TRANSCRIPTION_WORDS: int = 10
MIN_CAPTION_WORDS: int = 15  # минимум слов в описании для fallback (когда нет речи)
PROCESSING_TIMEOUT_SEC: int = 120

# Короткие коды категорий для callback_data (лимит 64 байта)
CATEGORY_TO_CODE: dict[str, str] = {
    "завтрак": "z",
    "основное блюдо": "o",
    "десерт": "d",
}
CODE_TO_CATEGORY: dict[str, str] = {v: k for k, v in CATEGORY_TO_CODE.items()}

# In-memory кэш для SHA и данных дубликатов (key -> data)
_callback_cache: dict[str, dict] = {}

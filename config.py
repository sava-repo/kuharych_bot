"""Загрузка конфигурации из .env"""

import os

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

# Admin access for test commands
ADMIN_IDS: list[int] = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_IDS", "").split(",")
    if uid.strip().isdigit()
]

# Testing environment (local or server)
TESTING_ENV: str = os.getenv("TESTING_ENV", "local")

# HikerAPI (скачивание Instagram Reels + получение описания)
HIKER_API_KEY: str = os.getenv("HIKER_API_KEY", "")

# Database
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "/data/bot.db")

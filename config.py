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

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Testing environment (local or server)
TESTING_ENV: str = os.getenv("TESTING_ENV", "local")

# HikerAPI (скачивание Instagram Reels + получение описания)
HIKER_API_KEY: str = os.getenv("HIKER_API_KEY", "")

# Database
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "/data/bot.db")

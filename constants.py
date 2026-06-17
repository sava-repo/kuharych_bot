"""Общие константы проекта"""

# ── Категории рецептов ──────────────────────────────────────────────────

VALID_CATEGORIES: list[str] = ["завтрак", "основное блюдо", "десерт"]

# Маппинг: текст кнопки меню → категория
MENU_BUTTON_TO_CATEGORY: dict[str, str] = {
    "🌅 Завтрак": "завтрак",
    "🍽 Основное блюдо": "основное блюдо",
    "🍰 Десерт": "десерт",
}

# Короткие коды категорий для callback_data (лимит 64 байта)
CATEGORY_TO_CODE: dict[str, str] = {
    "завтрак": "z",
    "основное блюдо": "o",
    "десерт": "d",
}
CODE_TO_CATEGORY: dict[str, str] = {v: k for k, v in CATEGORY_TO_CODE.items()}


def category_to_code(category: str) -> str:
    """Короткий код категории для callback_data"""
    return CATEGORY_TO_CODE.get(category, "o")


def code_to_category(code: str) -> str:
    """Категория по короткому коду"""
    return CODE_TO_CATEGORY.get(code, "основное блюдо")


# ── Лимиты ────────────────────────────────────────────────────────────────

MAX_VIDEO_DURATION_SEC: int = 180  # 3 минуты
MIN_TRANSCRIPTION_WORDS: int = 10
MIN_CAPTION_WORDS: int = 10  # минимум слов в описании для fallback (когда нет речи)
PROCESSING_TIMEOUT_SEC: int = 120

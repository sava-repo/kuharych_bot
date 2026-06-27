"""Общие константы проекта"""

# ── Стартовый набор категорий (сидируется в каждую новую группу) ────────
# is_default=True помечает категорию-амортизатор: в неё уходят рецепты при
# удалении других категорий и при добавлении уже известного рилса в новую
# группу. Default неудаляем — в группе всегда минимум одна категория.

DEFAULT_CATEGORIES: list[dict] = [
    {"name": "завтрак", "position": 0, "is_default": False},
    {"name": "основное блюдо", "position": 1, "is_default": True},
    {"name": "десерт", "position": 2, "is_default": False},
]

DEFAULT_CATEGORY_NAME: str = "основное блюдо"


def find_default(defaults: list[dict] | None = None) -> str:
    """Имя default-категории из набора DEFAULT_CATEGORIES."""
    for cat in defaults or DEFAULT_CATEGORIES:
        if cat.get("is_default"):
            return cat["name"]
    return DEFAULT_CATEGORY_NAME


# ── Лимиты категорий ─────────────────────────────────────────────────────

MAX_CATEGORIES_PER_GROUP: int = 30
MIN_CATEGORY_NAME_LEN: int = 1
MAX_CATEGORY_NAME_LEN: int = 50


# ── Лимиты обработки видео ───────────────────────────────────────────────

MAX_VIDEO_DURATION_SEC: int = 180  # 3 минуты
MIN_TRANSCRIPTION_WORDS: int = 10
MIN_CAPTION_WORDS: int = 10  # минимум слов в описании для fallback (когда нет речи)
PROCESSING_TIMEOUT_SEC: int = 120

"""Все кастомные исключения проекта"""

# ── Рецепты ─────────────────────────────────────────────────────────────


class RecipeNotFoundError(Exception):
    """Рецепт не найден."""
    pass


class NotARecipeError(Exception):
    """Видео не содержит рецепт."""
    pass


class RecipeParseError(Exception):
    """Ошибка парсинга ответа LLM."""
    pass


# ── Обработка видео ─────────────────────────────────────────────────────


class VideoTooLongError(Exception):
    """Видео слишком длинное."""
    pass


class VideoDownloadError(Exception):
    """Не удалось скачать видео."""
    pass


class SpeechNotRecognizedError(Exception):
    """Не удалось распознать речь в видео."""
    pass


class StorageUnavailableError(Exception):
    """База рецептов временно недоступна."""
    pass
"""Бизнес-логика пайплайна обработки видео.

Вынесена из handlers/link.py для разделения ответственности.
"""

import logging

from constants import MIN_CAPTION_WORDS, MIN_TRANSCRIPTION_WORDS
from exceptions import NotARecipeError, RecipeParseError, SpeechNotRecognizedError
from models.recipe import Recipe
from services import hiker, transcriber, recipe_parser
import services.group_manager as gm

logger = logging.getLogger(__name__)


def _clean_url(url: str) -> str:
    """Отрезает query-параметры (?igsh=..., ?utm=... и т.д.)."""
    return url.split("?")[0]


def _group_category_names(group_id: str) -> tuple[list[str], str]:
    """Возвращает (список имён категорий группы, имя default-категории)."""
    cats = gm.get_group_categories(group_id)
    names = [c.name for c in cats]
    default = next((c.name for c in cats if c.is_default), "")
    return names, default


def _resolve_category_id(group_id: str, category_name: str) -> int | None:
    """Переводит имя категории (ответ LLM) в category_id; при промахе — default."""
    cat = gm.get_category(group_id, category_name)
    if cat:
        return cat.category_id
    return gm.get_default_category_id(group_id)


class PipelineResult:
    """Результат обработки видео."""

    __slots__ = ("recipe", "recipe_id", "category_id", "duplicate_info", "source_url", "is_new")

    def __init__(
        self,
        recipe: Recipe,
        recipe_id: int,
        category_id: int | None,
        duplicate_info: dict | None,
        source_url: str,
        is_new: bool,
    ) -> None:
        self.recipe = recipe
        self.recipe_id = recipe_id
        self.category_id = category_id
        self.duplicate_info = duplicate_info
        self.source_url = source_url
        self.is_new = is_new


async def process_video(
    url: str, message_id: int, user_id: int, group_id: str
) -> PipelineResult:
    """
    Полный пайплайн обработки видео.

    Args:
        url: URL Instagram Reels
        message_id: ID сообщения (для имени временного файла)
        user_id: ID пользователя
        group_id: ID активной группы

    Returns:
        PipelineResult с данными рецепта

    Raises:
        SpeechNotRecognizedError: не удалось распознать речь
        NotARecipeError: видео не содержит рецепт
        RecipeParseError: ошибка парсинга ответа LLM
        RuntimeError: другие ошибки обработки
    """
    video_path: str | None = None
    clean_url = _clean_url(url)

    try:
        existing_recipe_id = gm.find_recipe_by_source(url)
        if existing_recipe_id:
            result = await _handle_existing_recipe(existing_recipe_id, group_id, url, user_id)
            if result is not None:
                return result

        video_path, caption = await hiker.download_reel(url, message_id)
        if caption:
            logger.info("Using HikerAPI caption (%s chars)", len(caption))
        else:
            logger.info("HikerAPI: no caption available")

        transcription = await transcriber.transcribe(video_path)

        word_count = len(transcription.split())
        if word_count < MIN_TRANSCRIPTION_WORDS:
            if caption and len(caption.split()) >= MIN_CAPTION_WORDS:
                logger.info(
                    "Speech too short (%s words), falling back to caption (%s words)",
                    word_count, len(caption.split()),
                )
                transcription = None
            else:
                raise SpeechNotRecognizedError("Не удалось распознать речь в видео")

        cat_names, default_name = _group_category_names(group_id)
        recipe = await recipe_parser.generate_recipe(
            transcription, caption, url, cat_names, default_name
        )

        duplicate = gm.check_duplicate(recipe.slug)
        category_id = _resolve_category_id(group_id, recipe.category)

        if duplicate:
            # Рецепт с таким slug уже есть в БД — привязываем к группе
            existing = gm.get_recipe_by_slug(recipe.slug)
            recipe_id = existing["recipe_id"] if existing else 0
            gm.register_source(url, recipe_id)
            gm.add_recipe_to_group(group_id, recipe_id, category_id, user_id)
            return PipelineResult(
                recipe=recipe,
                recipe_id=recipe_id,
                category_id=category_id,
                duplicate_info={"recipe_id": recipe_id},
                source_url=clean_url,
                is_new=True,
            )

        recipe_id = gm.save_recipe(
            slug=recipe.slug,
            title=recipe.title,
            content_md=recipe.to_markdown(created=""),
            source=clean_url,
            ingredients=recipe.ingredients,
            steps=recipe.steps,
        )

        gm.register_source(url, recipe_id)
        gm.add_recipe_to_group(group_id, recipe_id, category_id, user_id)

        return PipelineResult(
            recipe=recipe,
            recipe_id=recipe_id,
            category_id=category_id,
            duplicate_info=None,
            source_url=clean_url,
            is_new=True,
        )

    finally:
        if video_path:
            hiker.cleanup_file(video_path)


async def _handle_existing_recipe(
    recipe_id: int, group_id: str, url: str, user_id: int
) -> PipelineResult | None:
    """
    Обрабатывает случай, когда рецепт с таким reel ID уже существует.

    Контент переиспользуется (без повторного LLM-вызова); в новую группу
    рецепт добавляется под default-категорию.

    Returns:
        PipelineResult если рецепт загружен, None если нужно обработать заново
    """
    clean_url = _clean_url(url)

    recipe_data = gm.get_recipe(recipe_id)
    if not recipe_data:
        gm.unregister_source(url)
        return None

    # Если рецепт уже в этой группе — просто показываем его в его категории
    if gm.recipe_in_group(group_id, recipe_id):
        cat = gm.get_group_recipe_category(group_id, recipe_id)
        category_id = cat.category_id if cat else gm.get_default_category_id(group_id)
    else:
        # Добавляем в группу под default-категорию
        category_id = gm.get_default_category_id(group_id)
        gm.add_recipe_to_group(group_id, recipe_id, category_id, user_id)

    recipe = Recipe.from_markdown(recipe_data["content_md"], recipe_data["source"])
    return PipelineResult(
        recipe=recipe,
        recipe_id=recipe_id,
        category_id=category_id,
        duplicate_info=None,
        source_url=clean_url,
        is_new=False,
    )

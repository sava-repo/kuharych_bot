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


class PipelineResult:
    """Результат обработки видео."""

    __slots__ = ("recipe", "duplicate_info", "source_url", "is_new")

    def __init__(
        self,
        recipe: Recipe,
        duplicate_info: dict | None,
        source_url: str,
        is_new: bool,
    ) -> None:
        self.recipe = recipe
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

    try:
        existing = gm.find_recipe_by_source(url)
        if existing:
            result = await _handle_existing_recipe(existing, group_id, url)
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

        recipe = await recipe_parser.generate_recipe(transcription, caption, url)

        duplicate = gm.check_duplicate(recipe.category, recipe.slug)

        if duplicate:
            gm.register_source(url, recipe.category, recipe.slug)
            gm.add_recipe_to_group(group_id, recipe.category, recipe.slug)
            return PipelineResult(recipe, {"category": recipe.category, "slug": recipe.slug}, url, True)

        gm.save_recipe(
            category=recipe.category,
            slug=recipe.slug,
            title=recipe.title,
            content_md=recipe.to_markdown(created=""),
            source=url,
            ingredients=recipe.ingredients,
            steps=recipe.steps,
        )

        gm.register_source(url, recipe.category, recipe.slug)
        gm.add_recipe_to_group(group_id, recipe.category, recipe.slug)

        return PipelineResult(recipe, None, url, True)

    finally:
        if video_path:
            hiker.cleanup_file(video_path)


async def _handle_existing_recipe(
    existing: dict, group_id: str, url: str
) -> PipelineResult | None:
    """
    Обрабатывает случай, когда рецепт с таким source URL уже существует.

    Returns:
        PipelineResult если рецепт загружен, None если нужно обработать заново
    """
    category = existing["category"]
    slug = existing["slug"]

    group_slugs = gm.get_group_recipes_by_category(group_id, category)
    if slug in group_slugs:
        recipe_data = gm.get_recipe(category, slug)
        if not recipe_data:
            gm.unregister_source(url)
            return None
        recipe = Recipe.from_markdown(recipe_data["content_md"], category, url)
        return PipelineResult(recipe, None, url, False)

    gm.add_recipe_to_group(group_id, category, slug)
    recipe_data = gm.get_recipe(category, slug)
    if not recipe_data:
        logger.warning(
            "Recipe %s/%s not found in DB, unregistering source %s",
            category, slug, url,
        )
        gm.unregister_source(url)
        return None

    recipe = Recipe.from_markdown(recipe_data["content_md"], category, url)
    return PipelineResult(recipe, None, url, False)

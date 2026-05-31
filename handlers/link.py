"""Обработка входящих сообщений со ссылками на Reels"""

import asyncio
import logging
import re

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

import config
from services import hiker, transcriber, recipe_parser, gramax, cache
from services.recipe_parser import NotARecipeError, RecipeParseError
import services.group_manager as gm
from handlers.menu import MENU_KEYBOARD

logger = logging.getLogger(__name__)

router = Router()

# Regex для валидации ссылок (только Instagram)
URL_PATTERN = re.compile(
    r"https?://(www\.)?(m\.)?"
    r"instagram\.com"
    r"/\S+",
    re.IGNORECASE,
)


def _extract_url(text: str) -> str | None:
    """Извлекает URL из текста сообщения"""
    match = URL_PATTERN.search(text)
    return match.group(0) if match else None


def _cat_code(category: str) -> str:
    """Короткий код категории для callback_data"""
    return config.CATEGORY_TO_CODE.get(category, "o")


def _recipe_keyboard(category: str, slug: str) -> InlineKeyboardMarkup:
    """Клавиатура под рецептом"""
    rk = cache.put({"category": category, "slug": slug})
    cc = _cat_code(category)
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}")
    builder.adjust(2)
    return builder.as_markup()


def _duplicate_keyboard(category: str, slug: str, sha: str, recipe: object = None) -> InlineKeyboardMarkup:
    """Клавиатура при обнаружении дубликата
    
    Args:
        category: категория рецепта
        slug: slug рецепта
        sha: SHA файла в GitHub
        recipe: полный объект Recipe (для кнопки "Перезаписать")
    """
    # Сохраняем полный рецепт + sha в кэш
    rk = cache.put({
        "category": category, 
        "slug": slug, 
        "sha": sha,
        "recipe": recipe
    })
    cc = _cat_code(category)
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Перезаписать",
        callback_data=f"ow:{cc}:{rk}",
    )
    builder.button(
        text="📝 Сохранить как новый",
        callback_data=f"sn:{cc}:{rk}",
    )
    builder.adjust(2)
    return builder.as_markup()


_PROCESSING_DOTS = ["⏳ Обрабатываю.", "⏳ Обрабатываю..", "⏳ Обрабатываю..."]
_DOT_INTERVAL = 0.5  # секунды между сменой точек


async def _animate_dots(msg: Message) -> None:
    """Фоновая задача — анимирует точки в сообщении «Обрабатываю...»"""
    i = 0
    try:
        while True:
            await asyncio.sleep(_DOT_INTERVAL)
            try:
                await msg.edit_text(_PROCESSING_DOTS[i % len(_PROCESSING_DOTS)])
            except TelegramBadRequest:
                pass  # сообщение не изменилось или удалено — игнорируем
            i += 1
    except asyncio.CancelledError:
        pass  # нормальное завершение — задача отменена


@router.message(F.text, Command("start", "help"))
async def cmd_start(message: Message) -> None:
    """Обработка /start и /help"""
    await message.answer(
        "👋 Привет! Я бот для сохранения рецептов из Reels.\n\n"
        "Отправь мне ссылку на Instagram Reels — "
        "и я извлеку рецепт из видео.\n\n"
        "Используй кнопки меню внизу, чтобы получить случайный рецепт по категории.",
        reply_markup=MENU_KEYBOARD,
    )


@router.message(F.text)
async def handle_link(message: Message) -> None:
    """Обработка текстового сообщения — поиск ссылки и запуск пайплайна"""
    # Извлекаем URL
    url = _extract_url(message.text or "")
    if not url:
        await message.answer(
            "🔗 Отправьте ссылку на Instagram Reels"
        )
        return

    # Определяем пользователя и его активную группу
    user_id = message.from_user.id
    active_group_id = gm.get_user_active_group(user_id)

    # Запускаем обработку с анимацией точек
    processing_msg = await message.answer("⏳ Обрабатываю...")
    animation_task = asyncio.create_task(_animate_dots(processing_msg))

    try:
        result = await asyncio.wait_for(
            _process_video(url, message.message_id, user_id, active_group_id),
            timeout=config.PROCESSING_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        animation_task.cancel()
        await processing_msg.edit_text("⏰ Обработка заняла слишком много времени. Попробуйте снова")
        return
    except Exception as e:
        animation_task.cancel()
        logger.error(f"Processing error: {e}", exc_info=True)
        error_text = str(e)

        # Маппинг ошибок на пользовательские сообщения
        if "слишком длинное" in error_text:
            await processing_msg.edit_text(f"⏱ Видео слишком длинное (максимум 3 минуты)")
        elif "Не удалось скачать" in error_text:
            await processing_msg.edit_text("❌ Не удалось скачать видео. Попробуйте другую ссылку")
        elif "Не удалось распознать речь" in error_text:
            await processing_msg.edit_text("🔇 Не удалось распознать речь в видео")
        elif "не содержит рецепт" in error_text:
            await processing_msg.edit_text("🍳 Видео не содержит рецепт. Попробуйте другой рилс")
        elif "недоступна" in error_text:
            await processing_msg.edit_text("🗃 База рецептов временно недоступна. Попробуйте позже")
        else:
            await processing_msg.edit_text(f"❌ Произошла ошибка. Попробуйте позже")
        return
    finally:
        animation_task.cancel()

    recipe, duplicate_info, source_url, is_new = result

    if duplicate_info:
        # Дубликат — предлагаем выбор
        await processing_msg.edit_text(
            f"⚠️ Рецепт «{recipe.title}» уже существует в категории «{recipe.category}».\n\n"
            f"{recipe.format_message()}\n\n"
            f"Что делаем?",
            reply_markup=_duplicate_keyboard(
                recipe.category, recipe.slug, duplicate_info["sha"], recipe
            ),
        )
    else:
        # Успешно сохранено
        status = "✅ Рецепт сохранён!" if is_new else "✅ Рецепт добавлен в вашу коллекцию!"
        await processing_msg.edit_text(
            f"{status}\n\n{recipe.format_message()}",
            reply_markup=_recipe_keyboard(recipe.category, recipe.slug),
        )


async def _process_video(
    url: str, message_id: int, user_id: int, group_id: str
) -> tuple:
    """
    Полный пайплайн обработки видео.
    Возвращает (Recipe, duplicate_info | None, source_url, is_new)
    """
    video_path: str | None = None
    is_new = True

    try:
        # 0. Проверяем — может рецепт с таким source URL уже существует глобально
        existing = gm.find_recipe_by_source(url)
        if existing:
            category = existing["category"]
            slug = existing["slug"]

            try:
                # Проверяем, есть ли уже в этой группе
                group_slugs = gm.get_group_recipes_by_category(group_id, category)
                if slug in group_slugs:
                    # Рецепт уже в группе — загружаем и показываем
                    content = await gramax.get_recipe_content(category, f"{slug}.md")
                    recipe = _parse_recipe_from_markdown(content, category, url)
                    return recipe, None, url, False

                # Добавляем существующий рецепт в группу
                gm.add_recipe_to_group(group_id, category, slug)
                content = await gramax.get_recipe_content(category, f"{slug}.md")
                recipe = _parse_recipe_from_markdown(content, category, url)
                return recipe, None, url, False
            except gramax.RecipeNotFoundError:
                # Рецепт удалён из GitHub — убираем устаревшую запись и обрабатываем заново
                logger.warning(f"Recipe {category}/{slug} not found in GitHub, unregistering source {url}")
                gm.unregister_source(url)

        # 1. Скачиваем видео и получаем caption через HikerAPI
        video_path, caption = await hiker.download_reel(url, message_id)
        if caption:
            logger.info(f"Using HikerAPI caption ({len(caption)} chars)")
        else:
            logger.info("HikerAPI: no caption available")

        # 2. Транскрибация (ffmpeg sync + Groq async)
        transcription = await transcriber.transcribe(video_path)

        # Проверяем минимальную длину транскрипции
        word_count = len(transcription.split())
        if word_count < config.MIN_TRANSCRIPTION_WORDS:
            # Если речь не распознана — пробуем извлечь рецепт из описания
            if caption and len(caption.split()) >= config.MIN_CAPTION_WORDS:
                logger.info(
                    f"Speech too short ({word_count} words), "
                    f"falling back to caption ({len(caption.split())} words)"
                )
                transcription = None  # сигнализируем recipe_parser
            else:
                raise RuntimeError("Не удалось распознать речь в видео")

        # 3. Генерация рецепта
        recipe = await recipe_parser.generate_recipe(transcription, caption, url)

        # 4. Проверка дубликата по slug в GitHub
        duplicate = await gramax.check_duplicate(recipe.category, recipe.slug)

        if duplicate:
            # Файл уже есть в GitHub — регистрируем source и добавляем в группу
            gm.register_source(url, recipe.category, recipe.slug)
            gm.add_recipe_to_group(group_id, recipe.category, recipe.slug)
            return recipe, duplicate, url, True

        # 5. Сохранение в GitHub
        await gramax.save_recipe(recipe)

        # 6. Регистрируем source URL и добавляем в группу
        gm.register_source(url, recipe.category, recipe.slug)
        gm.add_recipe_to_group(group_id, recipe.category, recipe.slug)
        
        # 7. Индексируем ингредиенты для поиска
        gm.index_recipe_ingredients(recipe.category, recipe.slug, recipe.ingredients)

        return recipe, None, url, True

    finally:
        # Удаляем временные файлы
        if video_path:
            hiker.cleanup_file(video_path)


def _parse_recipe_from_markdown(md_content: str, category: str, source: str):
    """Парсит рецепт из Markdown (после загрузки из GitHub) в объект Recipe."""
    from models.recipe import Recipe

    lines = md_content.strip().split("\n")
    title = ""
    ingredients = []
    steps = []
    current_section = None

    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            continue
        if stripped.startswith("title:"):
            title = stripped.replace("title:", "").strip().strip('"')
            continue
        if stripped.startswith("category:") or stripped.startswith("source:") or stripped.startswith("created:") or stripped.startswith("tags:"):
            continue
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            continue
        if stripped.startswith("## Ингредиенты"):
            current_section = "ingredients"
            continue
        if stripped.startswith("## Способ приготовления"):
            current_section = "steps"
            continue
        if current_section == "ingredients" and stripped.startswith("- "):
            ingredients.append(stripped[2:])
        elif current_section == "steps" and stripped and stripped[0].isdigit() and "." in stripped:
            step_text = stripped.split(".", 1)[1].strip()
            if step_text:
                steps.append(step_text)

    return Recipe(
        title=title or "Без названия",
        ingredients=ingredients,
        steps=steps,
        category=category,
        source=source,
    )

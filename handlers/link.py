"""Обработка входящих сообщений со ссылками на Reels"""

import asyncio
import logging
import re

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from services import downloader, transcriber, recipe_parser, gramax
from services.recipe_parser import NotARecipeError, RecipeParseError
import services.group_manager as gm
from handlers.menu import MENU_KEYBOARD

logger = logging.getLogger(__name__)

router = Router()

# Regex для валидации ссылок
URL_PATTERN = re.compile(
    r"https?://(www\.)?(m\.)?"
    r"(instagram\.com|tiktok\.com|youtube\.com|youtu\.be)"
    r"/\S+",
    re.IGNORECASE,
)


def _extract_url(text: str) -> str | None:
    """Извлекает URL из текста сообщения"""
    match = URL_PATTERN.search(text)
    return match.group(0) if match else None


# Счётчик для генерации коротких ключей кэша
_cache_counter = 0


def _cache_recipe(category: str, slug: str) -> str:
    """Сохраняет рецепт в кэш, возвращает короткий ключ (r0, r1, ...)"""
    global _cache_counter
    key = f"r{_cache_counter}"
    _cache_counter += 1
    config._callback_cache[key] = {"category": category, "slug": slug}
    return key


def _cat_code(category: str) -> str:
    """Короткий код категории для callback_data"""
    return config.CATEGORY_TO_CODE.get(category, "o")


def _recipe_keyboard(category: str, slug: str, url: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура под рецептом"""
    rk = _cache_recipe(category, slug)
    cc = _cat_code(category)
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}")
    if url:
        builder.button(text="▶️ Открыть Reels", url=url)
        builder.adjust(2, 1)
    else:
        builder.adjust(2)
    return builder.as_markup()


def _duplicate_keyboard(category: str, slug: str, sha: str, url: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура при обнаружении дубликата"""
    rk = _cache_recipe(category, slug)
    # Сохраняем SHA отдельно в тот же ключ
    config._callback_cache[rk]["sha"] = sha
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
    if url:
        builder.button(text="▶️ Открыть Reels", url=url)
        builder.adjust(2, 1)
    else:
        builder.adjust(2)
    return builder.as_markup()


@router.message(F.text, Command("start", "help"))
async def cmd_start(message: Message) -> None:
    """Обработка /start и /help"""
    await message.answer(
        "👋 Привет! Я бот для сохранения рецептов из Reels.\n\n"
        "Отправь мне ссылку на Instagram Reels, TikTok или YouTube Shorts — "
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
            "🔗 Отправьте ссылку на Instagram Reels, TikTok или YouTube Shorts"
        )
        return

    # Определяем пользователя и его активную группу
    user_id = message.from_user.id
    active_group_id = gm.get_user_active_group(user_id)

    # Запускаем обработку
    processing_msg = await message.answer("⏳ Обрабатываю...")

    try:
        result = await asyncio.wait_for(
            _process_video(url, message.message_id, user_id, active_group_id),
            timeout=config.PROCESSING_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        await processing_msg.edit_text("⏰ Обработка заняла слишком много времени. Попробуйте снова")
        return
    except Exception as e:
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

    recipe, duplicate_info, source_url, is_new = result

    if duplicate_info:
        # Дубликат — предлагаем выбор
        await processing_msg.edit_text(
            f"⚠️ Рецепт «{recipe.title}» уже существует в категории «{recipe.category}».\n\n"
            f"{recipe.format_message()}\n\n"
            f"Что делаем?",
            reply_markup=_duplicate_keyboard(
                recipe.category, recipe.slug, duplicate_info["sha"], source_url
            ),
        )
    else:
        # Успешно сохранено
        status = "✅ Рецепт сохранён!" if is_new else "✅ Рецепт добавлен в вашу коллекцию!"
        await processing_msg.edit_text(
            f"{status}\n\n{recipe.format_message()}",
            reply_markup=_recipe_keyboard(recipe.category, recipe.slug, source_url),
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

        # 1. Скачивание (sync yt-dlp — запускаем в отдельном потоке)
        video_path, caption = await asyncio.to_thread(
            downloader.download_video, url, message_id
        )

        # 2. Транскрибация (ffmpeg sync + Groq async)
        transcription = await transcriber.transcribe(video_path)

        # Проверяем минимальную длину
        word_count = len(transcription.split())
        if word_count < config.MIN_TRANSCRIPTION_WORDS:
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

        return recipe, None, url, True

    finally:
        # Удаляем временные файлы
        if video_path:
            downloader.cleanup_file(video_path)


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

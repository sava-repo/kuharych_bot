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


def _recipe_keyboard(category: str, slug: str) -> InlineKeyboardMarkup:
    """Клавиатура под рецептом"""
    rk = _cache_recipe(category, slug)
    cc = _cat_code(category)
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}")
    builder.adjust(2)
    return builder.as_markup()


def _duplicate_keyboard(category: str, slug: str, sha: str) -> InlineKeyboardMarkup:
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
    # Проверка whitelist
    if message.chat.id not in config.WHITELIST_CHAT_IDS:
        logger.info(f"Ignored message from chat_id={message.chat.id} (not in whitelist)")
        return

    # Извлекаем URL
    url = _extract_url(message.text or "")
    if not url:
        await message.answer(
            "🔗 Отправьте ссылку на Instagram Reels, TikTok или YouTube Shorts"
        )
        return

    # Запускаем обработку
    processing_msg = await message.answer("⏳ Обрабатываю...")

    try:
        result = await asyncio.wait_for(
            _process_video(url, message.message_id),
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

    recipe, duplicate_info = result

    if duplicate_info:
        # Дубликат — предлагаем выбор
        await processing_msg.edit_text(
            f"⚠️ Рецепт «{recipe.title}» уже существует в категории «{recipe.category}».\n\n"
            f"{recipe.format_message()}\n\n"
            f"Что делаем?",
            reply_markup=_duplicate_keyboard(
                recipe.category, recipe.slug, duplicate_info["sha"]
            ),
        )
    else:
        # Успешно сохранено
        await processing_msg.edit_text(
            f"✅ Рецепт сохранён!\n\n{recipe.format_message()}",
            reply_markup=_recipe_keyboard(recipe.category, recipe.slug),
        )


async def _process_video(
    url: str, message_id: int
) -> tuple:
    """
    Полный пайплайн обработки видео.
    Возвращает (Recipe, duplicate_info | None)
    """
    video_path: str | None = None

    try:
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

        # 4. Проверка дубликата
        duplicate = await gramax.check_duplicate(recipe.category, recipe.slug)

        if duplicate:
            return recipe, duplicate

        # 5. Сохранение
        await gramax.save_recipe(recipe)

        return recipe, None

    finally:
        # Удаляем временные файлы
        if video_path:
            downloader.cleanup_file(video_path)
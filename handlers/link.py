"""Обработка входящих сообщений со ссылками на Reels"""

import asyncio
import logging
import re

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

import services.group_manager as gm
from constants import PROCESSING_TIMEOUT_SEC
from exceptions import (
    NotARecipeError,
    RecipeParseError,
    SpeechNotRecognizedError,
    StorageUnavailableError,
)
from services.recipe_pipeline import process_video
from handlers.keyboards import MENU_KEYBOARD, duplicate_keyboard, recipe_keyboard

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


# ── Анимация обработки ─────────────────────────────────────────────────

_PROCESSING_DOTS = ["⏳ Обрабатываю.", "⏳ Обрабатываю..", "⏳ Обрабатываю..."]
_DOT_INTERVAL = 0.5


async def _animate_dots(msg: Message) -> None:
    """Фоновая задача — анимирует точки в сообщении «Обрабатываю...»"""
    i = 0
    try:
        while True:
            await asyncio.sleep(_DOT_INTERVAL)
            try:
                await msg.edit_text(_PROCESSING_DOTS[i % len(_PROCESSING_DOTS)])
            except TelegramBadRequest:
                pass
            i += 1
    except asyncio.CancelledError:
        pass


# ── Маппинг исключений на пользовательские сообщения ──────────────────

def _error_message(exc: Exception) -> str:
    """Преобразует исключение в пользовательское сообщение."""
    if isinstance(exc, SpeechNotRecognizedError):
        return "🔇 Не удалось распознать речь в видео"
    if isinstance(exc, NotARecipeError):
        return "🍳 Видео не содержит рецепт. Попробуйте другой рилс"
    if isinstance(exc, StorageUnavailableError):
        return "🗃 База рецептов временно недоступна. Попробуйте позже"
    if isinstance(exc, RecipeParseError):
        return "❌ Не удалось извлечь рецепт из видео"
    error_text = str(exc)
    if "слишком длинное" in error_text:
        return "⏱ Видео слишком длинное (максимум 3 минуты)"
    if "Не удалось скачать" in error_text:
        return "❌ Не удалось скачать видео. Попробуйте другую ссылку"
    if "недоступна" in error_text:
        return "🗃 База рецептов временно недоступна. Попробуйте позже"
    return "❌ Произошла ошибка. Попробуйте позже"


# ── Хэндлеры ───────────────────────────────────────────────────────────

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
    url = _extract_url(message.text or "")
    if not url:
        await message.answer("🔗 Отправьте ссылку на Instagram Reels")
        return

    user_id = message.from_user.id
    active_group_id = gm.get_user_active_group(user_id)

    processing_msg = await message.answer("⏳ Обрабатываю...")
    animation_task = asyncio.create_task(_animate_dots(processing_msg))

    try:
        result = await asyncio.wait_for(
            process_video(url, message.message_id, user_id, active_group_id),
            timeout=PROCESSING_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        animation_task.cancel()
        await processing_msg.edit_text("⏰ Обработка заняла слишком много времени. Попробуйте снова")
        return
    except Exception as e:
        animation_task.cancel()
        logger.error("Processing error: %s", e, exc_info=True)
        await processing_msg.edit_text(_error_message(e))
        return
    finally:
        animation_task.cancel()

    if result.duplicate_info:
        await processing_msg.edit_text(
            f"⚠️ Рецепт «{result.recipe.title}» уже существует в категории «{result.recipe.category}».\n\n"
            f"{result.recipe.format_message()}\n\n"
            f"Что делаем?",
            reply_markup=duplicate_keyboard(
                result.recipe.category, result.recipe.slug,
                result.duplicate_info["sha"], result.recipe,
            ),
        )
    else:
        status = "✅ Рецепт сохранён!" if result.is_new else "✅ Рецепт добавлен в вашу коллекцию!"
        await processing_msg.edit_text(
            f"{status}\n\n{result.recipe.format_message()}",
            reply_markup=recipe_keyboard(result.recipe.category, result.recipe.slug),
        )
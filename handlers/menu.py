"""Persistent menu + случайный рецепт по категории"""

import logging
import random

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder

import config
import services.gramax as gramax

logger = logging.getLogger(__name__)

router = Router()

VALID_CATEGORIES = ["завтрак", "основное блюдо", "десерт"]

# Кнопки меню всегда видны внизу чата
MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌅 Завтрак")],
        [KeyboardButton(text="🍽 Основное блюдо")],
        [KeyboardButton(text="🍰 Десерт")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


def _parse_category(text: str) -> str | None:
    """Определяет категорию из текста кнопки"""
    mapping = {
        "🌅 Завтрак": "завтрак",
        "🍽 Основное блюдо": "основное блюдо",
        "🍰 Десерт": "десерт",
    }
    return mapping.get(text)


def _format_recipe_from_markdown(md_content: str) -> str:
    """Форматирует Markdown контент для отправки в чат"""
    lines = md_content.strip().split("\n")

    # Пропускаем YAML frontmatter
    in_frontmatter = False
    content_lines = []
    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        content_lines.append(line)

    # Убираем пустые строки в начале
    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)

    text = "\n".join(content_lines)

    # Убираем Markdown заголовки, заменяем на читаемый формат
    text = text.replace("## Ингредиенты", "📋 Ингредиенты:")
    text = text.replace("## Способ приготовления", "👨‍🍳 Приготовление:")
    text = text.replace("# ", "🍳 ")

    return text


@router.message(F.text.in_(["🌅 Завтрак", "🍽 Основное блюдо", "🍰 Десерт"]))
async def handle_menu_category(message: Message) -> None:
    """Обработка нажатия кнопки меню — случайный рецепт из категории"""
    if message.chat.id not in config.WHITELIST_CHAT_IDS:
        return

    category = _parse_category(message.text)
    if not category:
        return

    try:
        recipes = await gramax.list_recipes_in_category(category)
    except Exception as e:
        logger.error(f"List recipes error: {e}", exc_info=True)
        await message.answer("❌ База рецептов временно недоступна. Попробуйте позже")
        return

    if not recipes:
        await message.answer(
            f"📭 Пока нет рецептов в категории «{category}».\n"
            f"Отправьте мне ссылку на рилс с рецептом!"
        )
        return

    # Выбираем случайный рецепт
    random_recipe = random.choice(recipes)
    filename = random_recipe["name"]
    slug = filename.replace(".md", "")

    try:
        content = await gramax.get_recipe_content(category, filename)
    except Exception as e:
        logger.error(f"Get recipe error: {e}", exc_info=True)
        await message.answer("❌ Не удалось загрузить рецепт. Попробуйте позже")
        return

    formatted = _format_recipe_from_markdown(content)

    # Добавляем inline-кнопки
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"delete:{category}:{slug}")
    builder.button(
        text="🎲 Другой рецепт", callback_data=f"random:{category}"
    )
    builder.button(
        text="📂 Другая категория", callback_data=f"recat:{category}:{slug}"
    )
    builder.adjust(2, 1)

    await message.answer(
        f"🎲 Случайный рецепт:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("random:"))
async def handle_random_callback(callback: CallbackQuery) -> None:
    """Обработка кнопки 'Другой рецепт'"""
    if callback.message.chat.id not in config.WHITELIST_CHAT_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, category = parts

    await callback.answer("Выбираю другой рецепт...")

    try:
        recipes = await gramax.list_recipes_in_category(category)
    except Exception as e:
        logger.error(f"List recipes error: {e}", exc_info=True)
        await callback.message.edit_text("❌ База рецептов временно недоступна")
        return

    if not recipes:
        await callback.message.edit_text(
            f"📭 Пока нет рецептов в категории «{category}»"
        )
        return

    random_recipe = random.choice(recipes)
    filename = random_recipe["name"]
    slug = filename.replace(".md", "")

    try:
        content = await gramax.get_recipe_content(category, filename)
    except Exception as e:
        logger.error(f"Get recipe error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Не удалось загрузить рецепт")
        return

    formatted = _format_recipe_from_markdown(content)

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"delete:{category}:{slug}")
    builder.button(
        text="🎲 Другой рецепт", callback_data=f"random:{category}"
    )
    builder.button(
        text="📂 Другая категория", callback_data=f"recat:{category}:{slug}"
    )
    builder.adjust(2, 1)

    await callback.message.edit_text(
        f"🎲 Случайный рецепт:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )
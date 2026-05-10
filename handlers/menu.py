"""Persistent menu + случайный рецепт по категории"""

import logging
import random

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

import config
import services.gramax as gramax
import services.group_manager as gm

logger = logging.getLogger(__name__)

router = Router()

VALID_CATEGORIES = ["завтрак", "основное блюдо", "десерт"]

# Кнопки меню всегда видны внизу чата
MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌅 Завтрак")],
        [KeyboardButton(text="🍽 Основное блюдо")],
        [KeyboardButton(text="🍰 Десерт")],
        [KeyboardButton(text="👥 Мои группы")],
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


async def _try_get_random_recipe(group_id: str, category: str) -> tuple[str, str] | None:
    """
    Пытается получить случайный рецепт из категории.
    Если файл в GitHub не найден (404) — удаляет «мёртвую» запись и пробует другой.
    Возвращает (slug, content) или None.
    """
    group_slugs = gm.get_group_recipes_by_category(group_id, category)

    if not group_slugs:
        return None

    # Перемешиваем, чтобы не зациклиться на одном мёртвом рецепте
    random.shuffle(group_slugs)

    for slug in group_slugs:
        filename = f"{slug}.md"
        try:
            content = await gramax.get_recipe_content(category, filename)
            return slug, content
        except Exception as e:
            err_str = str(e)
            if "404" in err_str:
                # Рецепт удалён из GitHub — убираем из группы
                logger.warning(f"Stale recipe {category}/{slug} not found in GitHub, removing from group {group_id}")
                gm.remove_recipe_from_group(group_id, category, slug)
                continue
            # Другая ошибка — пробрасываем
            raise

    return None


@router.message(F.text.in_(["🌅 Завтрак", "🍽 Основное блюдо", "🍰 Десерт"]))
async def handle_menu_category(message: Message) -> None:
    """Обработка нажатия кнопки меню — случайный рецепт из категории"""
    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)
    category = _parse_category(message.text)
    if not category:
        return

    result = await _try_get_random_recipe(group_id, category)

    if not result:
        group = gm.get_group(group_id)
        group_name = group.name if group else "Неизвестная"
        await message.answer(
            f"📭 Пока нет рецептов в категории «{category}» в группе «{group_name}».\n"
            f"Отправьте мне ссылку на рилс с рецептом!"
        )
        return

    slug, content = result

    formatted = _format_recipe_from_markdown(content)

    # Добавляем inline-кнопки
    rk = f"r{len(config._callback_cache)}"
    config._callback_cache[rk] = {"category": category, "slug": slug, "group_id": group_id}

    cc = config.CATEGORY_TO_CODE.get(category, "o")
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(
        text="🎲 Другой рецепт", callback_data=f"rnd:{cc}"
    )
    builder.button(
        text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}"
    )
    builder.adjust(2, 1)

    await message.answer(
        f"🎲 Случайный рецепт:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("rnd:"))
async def handle_random_callback(callback: CallbackQuery) -> None:
    """Обработка кнопки 'Другой рецепт'"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)

    parts = callback.data.split(":")
    if len(parts) != 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc = parts
    category = config.CODE_TO_CATEGORY.get(cc, "основное блюдо")

    await callback.answer("Выбираю другой рецепт...")

    result = await _try_get_random_recipe(group_id, category)

    if not result:
        await callback.message.edit_text(
            f"📭 Пока нет рецептов в категории «{category}»"
        )
        return

    slug, content = result

    formatted = _format_recipe_from_markdown(content)

    rk = f"r{len(config._callback_cache)}"
    config._callback_cache[rk] = {"category": category, "slug": slug, "group_id": group_id}

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(
        text="🎲 Другой рецепт", callback_data=f"rnd:{cc}"
    )
    builder.button(
        text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}"
    )
    builder.adjust(2, 1)

    await callback.message.edit_text(
        f"🎲 Случайный рецепт:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )
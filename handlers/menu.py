"""Persistent menu + случайный рецепт по категории"""

import logging
import random

from aiogram import Router, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import services.gramax as gramax
import services.group_manager as gm
import services.cache as cache
import services.rotation as rotation
from constants import (
    MENU_BUTTON_TO_CATEGORY,
    VALID_CATEGORIES,
    category_to_code,
    code_to_category,
)
from handlers.keyboards import MENU_KEYBOARD

logger = logging.getLogger(__name__)

router = Router()


class SearchState(StatesGroup):
    waiting_for_ingredient = State()


def _parse_category(text: str) -> str | None:
    """Определяет категорию из текста кнопки"""
    return MENU_BUTTON_TO_CATEGORY.get(text)


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


def _build_recipe_inline(category: str, slug: str, group_id: str, rk: str, *, extra_btn: tuple[str, str] | None = None) -> InlineKeyboardBuilder:
    """Строит inline-клавиатуру для случайного/найденного рецепта."""
    cc = category_to_code(category)
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{cc}:{rk}")

    source_url = gm.find_source_by_slug(category, slug)
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    if extra_btn:
        builder.button(text=extra_btn[0], callback_data=extra_btn[1])

    if source_url:
        builder.adjust(3, 1)
    else:
        builder.adjust(2, 1)

    return builder


async def _try_get_random_recipe(
    group_id: str, category: str, *, exclude: list[str] | None = None
) -> tuple[str, str] | None:
    """
    Пытается получить случайный рецепт из категории.
    Если файл в GitHub не найден (404) — пропускает «мёртвую» запись и пробует другой.
    Возвращает (slug, content) или None.
    """
    group_slugs = gm.get_group_recipes_by_category(group_id, category)
    if not group_slugs:
        return None

    if exclude:
        exclude_set = set(exclude)
        filtered = [s for s in group_slugs if s not in exclude_set]
        if filtered:
            group_slugs = filtered

    random.shuffle(group_slugs)

    for slug in group_slugs:
        try:
            content = await gramax.get_recipe_content(category, f"{slug}.md")
            return slug, content
        except gramax.RecipeNotFoundError:
            logger.warning("Stale recipe %s/%s not found in GitHub, skipping", category, slug)
            continue

    return None


async def _try_get_recipe_from_slugs(
    slugs: list[str], category: str, *, exclude: list[str] | None = None
) -> tuple[str, str] | None:
    """
    Пытается получить рецепт из списка slugs.
    Возвращает (slug, content) или None.
    """
    if not slugs:
        return None

    if exclude:
        exclude_set = set(exclude)
        filtered = [s for s in slugs if s not in exclude_set]
        if filtered:
            slugs = filtered

    random.shuffle(slugs)

    for slug in slugs:
        try:
            content = await gramax.get_recipe_content(category, f"{slug}.md")
            return slug, content
        except gramax.RecipeNotFoundError:
            logger.warning("Stale recipe %s/%s not found in GitHub, skipping", category, slug)
            continue

    return None


# ── Хэндлеры категорий ─────────────────────────────────────────────────

@router.message(F.text.in_(["🌅 Завтрак", "🍽 Основное блюдо", "🍰 Десерт"]))
async def handle_menu_category(message: Message) -> None:
    """Обработка нажатия кнопки меню — случайный рецепт из категории"""
    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)
    category = _parse_category(message.text)
    if not category:
        return

    excluded = rotation.get_excluded(user_id, category)
    result = await _try_get_random_recipe(group_id, category, exclude=excluded)

    if not result:
        group = gm.get_group(group_id)
        group_name = group.name if group else "Неизвестная"
        await message.answer(
            f"📭 Пока нет рецептов в категории «{category}» в группе «{group_name}».\n"
            f"Отправьте мне ссылку на рилс с рецептом!"
        )
        return

    slug, content = result

    total_count = len(gm.get_group_recipes_by_category(group_id, category))
    rotation.add(user_id, category, slug, total_count)

    formatted = _format_recipe_from_markdown(content)
    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})
    cc = category_to_code(category)

    builder = _build_recipe_inline(category, slug, group_id, rk, extra_btn=("🎲 Другой рецепт", f"rnd:{cc}"))

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
    category = code_to_category(cc)

    await callback.answer("Выбираю другой рецепт...")

    excluded = rotation.get_excluded(user_id, category)
    result = await _try_get_random_recipe(group_id, category, exclude=excluded)

    if not result:
        await callback.message.edit_text(f"📭 Пока нет рецептов в категории «{category}»")
        return

    slug, content = result

    total_count = len(gm.get_group_recipes_by_category(group_id, category))
    rotation.add(user_id, category, slug, total_count)

    formatted = _format_recipe_from_markdown(content)
    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})

    builder = _build_recipe_inline(category, slug, group_id, rk, extra_btn=("🎲 Другой рецепт", f"rnd:{cc}"))

    await callback.message.edit_text(
        f"🎲 Случайный рецепт:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )


# ── Поиск по ингредиенту ────────────────────────────────────────────────

@router.message(F.text == "🔍 Поиск")
async def handle_search_start(message: Message, state: FSMContext) -> None:
    """Начало поиска по ингредиенту"""
    await message.answer("🔎 Введите ингредиент для поиска:")
    await state.set_state(SearchState.waiting_for_ingredient)


@router.message(SearchState.waiting_for_ingredient)
async def handle_search_ingredient(message: Message, state: FSMContext) -> None:
    """Обработка ввода ингредиента"""
    ingredient = message.text.strip()
    if not ingredient:
        await message.answer("Пожалуйста, введите ингредиент:")
        return

    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)

    await state.clear()

    cache_key = cache.put({"ingredient": ingredient, "group_id": group_id})

    builder = InlineKeyboardBuilder()
    for cat in VALID_CATEGORIES:
        cc = category_to_code(cat)
        builder.button(text=cat.capitalize(), callback_data=f"srch:{cc}:{cache_key}")
    builder.adjust(1)

    await message.answer(
        f"🔎 Выберите категорию для поиска «{ingredient}»:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("srch:"))
async def handle_search_category(callback: CallbackQuery) -> None:
    """Выполнение поиска по выбранной категории"""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc, cache_key = parts
    cached = cache.get(cache_key)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Попробуйте снова")
        return

    ingredient = cached["ingredient"]
    group_id = cached["group_id"]
    category = code_to_category(cc)
    user_id = callback.from_user.id

    await callback.answer(f"Ищу {ingredient}...")

    slugs = gm.search_recipes_by_ingredient(group_id, ingredient, category)

    if not slugs:
        await callback.message.edit_text(
            f"📭 Рецептов с ингредиентом «{ingredient}» в категории «{category}» не найдено"
        )
        return

    excluded = rotation.get_excluded(user_id, category)
    result = await _try_get_recipe_from_slugs(slugs, category, exclude=excluded)

    if not result:
        await callback.message.edit_text(
            f"📭 Не удалось загрузить рецепты с ингредиентом «{ingredient}» в категории «{category}»"
        )
        return

    slug, content = result
    rotation.add(user_id, category, slug, len(slugs))

    formatted = _format_recipe_from_markdown(content)
    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})

    builder = _build_recipe_inline(
        category, slug, group_id, rk,
        extra_btn=("🎲 Другой рецепт", f"srnd:{cc}:{cache_key}"),
    )

    await callback.message.edit_text(
        f"🔎 Результат поиска «{ingredient}»:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("srnd:"))
async def handle_search_random(callback: CallbackQuery) -> None:
    """Другой результат поиска"""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc, cache_key = parts
    cached = cache.get(cache_key)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Попробуйте снова")
        return

    ingredient = cached["ingredient"]
    group_id = cached["group_id"]
    category = code_to_category(cc)
    user_id = callback.from_user.id

    await callback.answer("Выбираю другой рецепт...")

    slugs = gm.search_recipes_by_ingredient(group_id, ingredient, category)

    if not slugs:
        await callback.message.edit_text(
            f"📭 Рецептов с ингредиентом «{ingredient}» в категории «{category}» не найдено"
        )
        return

    excluded = rotation.get_excluded(user_id, category)
    result = await _try_get_recipe_from_slugs(slugs, category, exclude=excluded)

    if not result:
        await callback.message.edit_text(
            f"📭 Не удалось загрузить рецепты с ингредиентом «{ingredient}» в категории «{category}»"
        )
        return

    slug, content = result
    rotation.add(user_id, category, slug, len(slugs))

    formatted = _format_recipe_from_markdown(content)
    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})

    builder = _build_recipe_inline(
        category, slug, group_id, rk,
        extra_btn=("🎲 Другой рецепт", f"srnd:{cc}:{cache_key}"),
    )

    await callback.message.edit_text(
        f"🔎 Результат поиска «{ingredient}»:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )
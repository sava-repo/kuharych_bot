"""Persistent menu + случайный рецепт по категории + полнотекстовый поиск"""

import logging
import random

from aiogram import Router, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import services.group_manager as gm
import services.cache as cache
import services.rotation as rotation
from models.recipe import Recipe
from constants import (
    MENU_BUTTON_TO_CATEGORY,
    category_to_code,
    code_to_category,
)
from handlers.keyboards import MENU_KEYBOARD, search_pagination_keyboard

logger = logging.getLogger(__name__)

router = Router()

SEARCH_PAGE_SIZE = 5


class SearchState(StatesGroup):
    waiting_for_query = State()


def _parse_category(text: str) -> str | None:
    """Определяет категорию из текста кнопки"""
    return MENU_BUTTON_TO_CATEGORY.get(text)


# ── Хэндлеры категорий ─────────────────────────────────────────────────

@router.message(F.text.in_(["🌅 Завтрак", "🍽 Основное блюдо", "🍰 Десерт"]))
async def handle_menu_category(message: Message) -> None:
    """Обработка нажатия кнопки меню — случайный рецепт из категории"""
    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)
    category = _parse_category(message.text)
    if not category:
        return

    group_slugs = gm.get_group_recipes_by_category(group_id, category)
    if not group_slugs:
        group = gm.get_group(group_id)
        group_name = group.name if group else "Неизвестная"
        await message.answer(
            f"📭 Пока нет рецептов в категории «{category}» в группе «{group_name}».\n"
            f"Отправьте мне ссылку на рилс с рецептом!"
        )
        return

    excluded = rotation.get_excluded(user_id, category)
    filtered = [s for s in group_slugs if s not in set(excluded)]
    candidates = filtered if filtered else group_slugs

    slug = random.choice(candidates)
    rotation.add(user_id, category, slug, len(group_slugs))

    recipe_data = gm.get_recipe(category, slug)
    if not recipe_data:
        await message.answer("📭 Не удалось загрузить рецепт. Попробуйте снова")
        return

    recipe = Recipe.from_markdown(recipe_data["content_md"], category, recipe_data["source"])
    rk = cache.put_recipe(category, slug)
    cc = category_to_code(category)

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{cc}:{rk}")

    source_url = gm.find_source_by_slug(category, slug)
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    builder.button(text="🎲 Другой рецепт", callback_data=f"rnd:{cc}")
    builder.adjust(3, 1) if source_url else builder.adjust(2, 1)

    await message.answer(
        f"🎲 Случайный рецепт:\n\n{recipe.format_message()}",
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

    group_slugs = gm.get_group_recipes_by_category(group_id, category)
    if not group_slugs:
        await callback.message.edit_text(f"📭 Пока нет рецептов в категории «{category}»")
        return

    excluded = rotation.get_excluded(user_id, category)
    filtered = [s for s in group_slugs if s not in set(excluded)]
    candidates = filtered if filtered else group_slugs

    slug = random.choice(candidates)
    rotation.add(user_id, category, slug, len(group_slugs))

    recipe_data = gm.get_recipe(category, slug)
    if not recipe_data:
        await callback.message.edit_text("📭 Не удалось загрузить рецепт. Попробуйте снова")
        return

    recipe = Recipe.from_markdown(recipe_data["content_md"], category, recipe_data["source"])
    rk = cache.put_recipe(category, slug)

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{cc}:{rk}")

    source_url = gm.find_source_by_slug(category, slug)
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    builder.button(text="🎲 Другой рецепт", callback_data=f"rnd:{cc}")
    builder.adjust(3, 1) if source_url else builder.adjust(2, 1)

    await callback.message.edit_text(
        f"🎲 Случайный рецепт:\n\n{recipe.format_message()}",
        reply_markup=builder.as_markup(),
    )


# ── Полнотекстовый поиск ────────────────────────────────────────────────

@router.message(F.text == "🔍 Поиск")
async def handle_search_start(message: Message, state: FSMContext) -> None:
    """Начало поиска"""
    await message.answer("🔎 Введите запрос для поиска:")
    await state.set_state(SearchState.waiting_for_query)


@router.message(SearchState.waiting_for_query)
async def handle_search_query(message: Message, state: FSMContext) -> None:
    """Обработка поискового запроса"""
    query = message.text.strip()
    if not query:
        await message.answer("Пожалуйста, введите запрос:")
        return

    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)

    await state.clear()

    results = gm.search_recipes_fulltext(group_id, query)

    if not results:
        await message.answer(f"📭 По запросу «{query}» ничего не найдено")
        return

    page = 0
    page_results = results[page * SEARCH_PAGE_SIZE:(page + 1) * SEARCH_PAGE_SIZE]
    total_pages = (len(results) + SEARCH_PAGE_SIZE - 1) // SEARCH_PAGE_SIZE

    cache_key = cache.put({
        "results": results,
        "query": query,
        "group_id": group_id,
    })

    recipe_ids = []
    for cat, slug, title in page_results:
        rid = cache.put_recipe(cat, slug)
        recipe_ids.append(rid)

    text = _format_search_results(query, page_results, recipe_ids, page, total_pages)
    kb = search_pagination_keyboard(cache_key, page, len(results))

    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("spage:"))
async def handle_search_page(callback: CallbackQuery) -> None:
    """Пагинация результатов поиска"""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cache_key, page_str = parts
    page = int(page_str)
    cached = cache.get(cache_key)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Попробуйте снова")
        return

    results = cached["results"]
    query = cached["query"]
    total = len(results)
    total_pages = (total + SEARCH_PAGE_SIZE - 1) // SEARCH_PAGE_SIZE

    page_results = results[page * SEARCH_PAGE_SIZE:(page + 1) * SEARCH_PAGE_SIZE]

    recipe_ids = []
    for cat, slug, title in page_results:
        rid = cache.put_recipe(cat, slug)
        recipe_ids.append(rid)

    text = _format_search_results(query, page_results, recipe_ids, page, total_pages)
    kb = search_pagination_keyboard(cache_key, page, total)

    await callback.message.edit_text(text, reply_markup=kb)


def _format_search_results(
    query: str,
    page_results: list[tuple[str, str, str]],
    recipe_ids: list[int],
    page: int,
    total_pages: int,
) -> str:
    """Форматирует страницу результатов поиска."""
    lines = [f"🔎 Результаты поиска «{query}»:\n"]

    for i, (cat, slug, title) in enumerate(page_results):
        rid = recipe_ids[i]
        lines.append(f"{title}")
        lines.append(f"Открыть: /open{rid}")
        lines.append("")

    if total_pages > 1:
        lines.append(f"Страница {page + 1} из {total_pages}")

    return "\n".join(lines).strip()


# ── Открытие рецепта по /open{key} ──────────────────────────────────────

@router.message(F.text.regexp(r"^/open\d+$"))
async def handle_open_recipe(message: Message) -> None:
    """Открытие рецепта по /open{key}"""
    key = message.text[5:]
    cached = cache.get(key)
    if not cached:
        await message.answer("❌ Рецепт не найден. Попробуйте поиск заново")
        return

    category = cached["category"]
    slug = cached["slug"]

    recipe_data = gm.get_recipe(category, slug)
    if not recipe_data:
        await message.answer("❌ Рецепт не найден")
        return

    recipe = Recipe.from_markdown(recipe_data["content_md"], category, recipe_data["source"])
    cc = category_to_code(category)
    rk = int(key)

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{cc}:{rk}")

    source_url = gm.find_source_by_slug(category, slug)
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    builder.adjust(2, 1) if source_url else builder.adjust(2)

    await message.answer(
        recipe.format_message(),
        reply_markup=builder.as_markup(),
    )

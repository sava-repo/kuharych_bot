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
from handlers.keyboards import build_menu_keyboard, search_pagination_keyboard

logger = logging.getLogger(__name__)

router = Router()

SEARCH_PAGE_SIZE = 5


class SearchState(StatesGroup):
    waiting_for_query = State()


# Команды reply-клавиатуры, которые не должны трактоваться как категории
_MENU_COMMANDS = {"🔍 Поиск", "👥 Группы", "🗂 Категории"}


async def category_button_filter(message: Message) -> dict | bool:
    """Матчит сообщение с кнопкой-категорией активной группы.

    Возвращает {"category": Category} или False. URL и команды пропускает,
    чтобы их обработали другие роутеры (link/группы/категории).
    """
    text = message.text
    if not text or text in _MENU_COMMANDS:
        return False
    if text.startswith("/") or "://" in text:
        return False
    group_id = gm.get_user_active_group(message.from_user.id)
    cat = gm.get_category(group_id, text)
    if cat:
        return {"category": cat}
    return False


# ── Выбор случайного рецепта ───────────────────────────────────────────

def _pick_random_recipe(
    user_id: int, group_id: str, category_id: int, category_name: str
) -> dict | None:
    """Выбирает случайный валидный рецепт с учётом rotation."""
    recipe_ids = gm.get_group_recipes_by_category(group_id, category_id)
    if not recipe_ids:
        return None

    pairs = [(rid, gm.get_recipe(rid)) for rid in recipe_ids]
    valid = [(rid, data) for rid, data in pairs if data]
    orphans = [rid for rid, data in pairs if not data]
    if orphans:
        logger.warning(
            "Orphan recipe ids skipped (missing in recipes): "
            "group=%s category_id=%s ids=%s",
            group_id, category_id, orphans,
        )
    if not valid:
        return None

    excluded = set(rotation.get_excluded(user_id, category_id))
    candidates = [p for p in valid if p[0] not in excluded] or valid

    recipe_id, recipe_data = random.choice(candidates)
    rotation.add(user_id, category_id, recipe_id, len(valid))

    recipe = Recipe.from_markdown(recipe_data["content_md"], recipe_data["source"])
    return {
        "recipe": recipe,
        "recipe_id": recipe_id,
        "source_url": gm.find_source_by_recipe_id(recipe_id),
        "rk": cache.put_recipe(recipe_id, group_id),
        "category_id": category_id,
        "category_name": category_name,
    }


def _random_recipe_markup(result: dict):
    """Inline-клавиатура для сообщения со случайным рецептом."""
    rk = result["rk"]
    category_id = result["category_id"]
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{rk}")

    source_url = result["source_url"]
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    builder.button(text="🎲 Другой рецепт", callback_data=f"rnd:{category_id}")

    builder.adjust(3, 1) if source_url else builder.adjust(2, 1)
    return builder.as_markup()


# ── Хэндлеры категорий ─────────────────────────────────────────────────
# ВНИМАНИЕ: handle_menu_category регистрируется ПОСЛЕ search/open-хендлеров
# (ниже в файле), чтобы ввод названия категории во время FSM поиска не
# перехватывался этим хендлером.


@router.callback_query(F.data.startswith("rnd:"))
async def handle_random_callback(callback: CallbackQuery) -> None:
    """Обработка кнопки 'Другой рецепт'"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)

    parts = callback.data.split(":")
    if len(parts) != 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, category_id_str = parts
    category_id = int(category_id_str)
    category = gm.get_category_by_id(category_id)
    category_name = category.name if category else "—"

    await callback.answer()

    result = _pick_random_recipe(user_id, group_id, category_id, category_name)
    if not result:
        await callback.message.edit_text(f"📭 Пока нет рецептов в категории «{category_name}»")
        return

    await callback.message.edit_text(
        f"🎲 Случайный рецепт:\n\n{result['recipe'].format_message(result['category_name'])}",
        reply_markup=_random_recipe_markup(result),
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
    active_group_id = gm.get_user_active_group(user_id)
    group_ids = [g.group_id for g in gm.get_user_groups(user_id)]

    await state.clear()

    results = gm.search_recipes_fulltext(
        group_ids, query, prefer_group_id=active_group_id
    )

    if not results:
        await message.answer(f"📭 По запросу «{query}» ничего не найдено")
        return

    page = 0
    page_results = results[page * SEARCH_PAGE_SIZE:(page + 1) * SEARCH_PAGE_SIZE]
    total_pages = (len(results) + SEARCH_PAGE_SIZE - 1) // SEARCH_PAGE_SIZE

    cache_key = cache.put({
        "results": results,
        "query": query,
    })

    recipe_ids = []
    for rid, slug, title, recipe_group_id in page_results:
        rkey = cache.put_recipe(rid, recipe_group_id)
        recipe_ids.append(rkey)

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
    for rid, slug, title, recipe_group_id in page_results:
        rkey = cache.put_recipe(rid, recipe_group_id)
        recipe_ids.append(rkey)

    text = _format_search_results(query, page_results, recipe_ids, page, total_pages)
    kb = search_pagination_keyboard(cache_key, page, total)

    await callback.message.edit_text(text, reply_markup=kb)


def _format_search_results(
    query: str,
    page_results: list[tuple[int, str, str, str]],
    recipe_ids: list[int],
    page: int,
    total_pages: int,
) -> str:
    """Форматирует страницу результатов поиска."""
    lines = [f"🔎 Результаты поиска «{query}»:\n"]

    for i, (rid, slug, title, group_id) in enumerate(page_results):
        rkey = recipe_ids[i]
        lines.append(f"{title}")
        lines.append(f"Открыть: /open{rkey}")
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

    recipe_id = cached["recipe_id"]
    group_id = cached.get("group_id") or gm.get_user_active_group(message.from_user.id)

    recipe_data = gm.get_recipe(recipe_id)
    if not recipe_data:
        await message.answer("❌ Рецепт не найден")
        return

    recipe = Recipe.from_markdown(recipe_data["content_md"], recipe_data["source"])

    category = gm.get_group_recipe_category(group_id, recipe_id)
    category_name = category.name if category else None
    source_url = gm.find_source_by_recipe_id(recipe_id)

    rk = cache.put_recipe(recipe_id, group_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{rk}")
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)
    builder.adjust(2, 1) if source_url else builder.adjust(2)

    await message.answer(
        recipe.format_message(category_name),
        reply_markup=builder.as_markup(),
    )


# ── Хэндлер кнопок-категорий (регистрируется последним, чтобы не перехватывать
# ввод во время FSM поиска или других состояний).


@router.message(category_button_filter)
async def handle_menu_category(message: Message, category) -> None:
    """Обработка нажатия кнопки меню — случайный рецепт из категории"""
    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)

    result = _pick_random_recipe(user_id, group_id, category.category_id, category.name)
    if not result:
        group = gm.get_group(group_id)
        group_name = group.name if group else "Неизвестная"
        await message.answer(
            f"📭 Пока нет рецептов в категории «{category.name}» в группе «{group_name}».\n"
            f"Отправьте мне ссылку на рилс с рецептом!"
        )
        return

    await message.answer(
        f"🎲 Случайный рецепт:\n\n{result['recipe'].format_message(result['category_name'])}",
        reply_markup=_random_recipe_markup(result),
    )

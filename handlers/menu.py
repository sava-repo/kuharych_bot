"""Persistent menu + случайный рецепт по категории + полнотекстовый поиск"""

import logging
import random
import re

from aiogram import Router, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import services.group_manager as gm
import services.rotation as rotation
from models.recipe import Recipe
from handlers.keyboards import (
    build_menu_keyboard,
    search_pagination_keyboard,
    add_portions_row,
)

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
        "group_id": group_id,
        "source_url": gm.find_source_by_recipe_id(recipe_id),
        "category_id": category_id,
        "category_name": category_name,
    }


def _random_recipe_markup(result: dict):
    """Inline-клавиатура для сообщения со случайным рецептом."""
    ref = f"{result['recipe_id']}:{result['group_id']}"
    category_id = result["category_id"]
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{ref}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{ref}")

    source_url = result["source_url"]
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    builder.button(text="🎲 Другой рецепт", callback_data=f"rnd:{category_id}")

    builder.adjust(3, 1) if source_url else builder.adjust(2, 1)
    add_portions_row(builder, ref, result["recipe"].portions)
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

    text = _format_search_results(query, page_results, page, total_pages)
    kb = search_pagination_keyboard(page, len(results))

    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("spage:"))
async def handle_search_page(callback: CallbackQuery) -> None:
    """Пагинация результатов поиска.

    Stateless: поисковый запрос извлекается из текста самого сообщения, поиск
    перевыполняется. Не зависит от in-memory кэша — переживает рестарт.
    """
    parts = callback.data.split(":")
    if len(parts) != 2:
        await callback.answer("Данные устарели", show_alert=True)
        return
    try:
        page = int(parts[1])
    except ValueError:
        await callback.answer("Данные устарели", show_alert=True)
        return

    query = _extract_search_query(callback.message.text or "")
    if query is None:
        await callback.answer("Данные устарели. Начните поиск заново", show_alert=True)
        return

    user_id = callback.from_user.id
    active_group_id = gm.get_user_active_group(user_id)
    group_ids = [g.group_id for g in gm.get_user_groups(user_id)]
    results = gm.search_recipes_fulltext(group_ids, query, prefer_group_id=active_group_id)
    if not results:
        await callback.message.edit_text(f"📭 По запросу «{query}» ничего не найдено")
        return

    total_pages = (len(results) + SEARCH_PAGE_SIZE - 1) // SEARCH_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    page_results = results[page * SEARCH_PAGE_SIZE:(page + 1) * SEARCH_PAGE_SIZE]

    text = _format_search_results(query, page_results, page, total_pages)
    kb = search_pagination_keyboard(page, len(results))

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=kb)


_SEARCH_QUERY_RE = re.compile(r"«([^»]*)»")


def _extract_search_query(text: str) -> str | None:
    """Достаёт поисковый запрос из текста сообщения с результатами поиска."""
    match = _SEARCH_QUERY_RE.search(text)
    return match.group(1) if match else None


def _format_search_results(
    query: str,
    page_results: list[tuple[int, str, str, str]],
    page: int,
    total_pages: int,
) -> str:
    """Форматирует страницу результатов поиска.

    Каждый рецепт доступен через ``/open{recipe_id}`` — глубокая ссылка не
    зависит от кэша и переживает рестарт процесса.
    """
    lines = [f"🔎 Результаты поиска «{query}»:\n"]

    for rid, slug, title, group_id in page_results:
        lines.append(title)
        lines.append(f"Открыть: /open{rid}")
        lines.append("")

    if total_pages > 1:
        lines.append(f"Страница {page + 1} из {total_pages}")

    return "\n".join(lines).strip()


# ── Открытие рецепта по /open{recipe_id} ────────────────────────────────

@router.message(F.text.regexp(r"^/open\d+$"))
async def handle_open_recipe(message: Message) -> None:
    """Открытие рецепта по /open{recipe_id} (без обращения к кэшу)."""
    recipe_id = int(message.text[5:])

    recipe_data = gm.get_recipe(recipe_id)
    if not recipe_data:
        await message.answer("❌ Рецепт не найден")
        return

    group_id = _resolve_recipe_group(message.from_user.id, recipe_id)

    recipe = Recipe.from_markdown(recipe_data["content_md"], recipe_data["source"])

    category = gm.get_group_recipe_category(group_id, recipe_id)
    category_name = category.name if category else None
    source_url = gm.find_source_by_recipe_id(recipe_id)

    ref = f"{recipe_id}:{group_id}"
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{ref}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{ref}")
    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)
    builder.adjust(2, 1) if source_url else builder.adjust(2)
    add_portions_row(builder, ref, recipe.portions)

    await message.answer(
        recipe.format_message(category_name),
        reply_markup=builder.as_markup(),
    )


def _resolve_recipe_group(user_id: int, recipe_id: int) -> str:
    """Группа для показа рецепта: активная, а если рецепта в ней нет — любая
    группа пользователя, содержащая рецепт (фолбэк для кросс-групповых ссылок)."""
    active = gm.get_user_active_group(user_id)
    if gm.recipe_in_group(active, recipe_id):
        return active
    for g in gm.get_user_groups(user_id):
        if gm.recipe_in_group(g.group_id, recipe_id):
            return g.group_id
    return active


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

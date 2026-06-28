"""Общие функции построения клавиатур для Telegram-бота"""

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import services.cache as cache
import services.group_manager as gm


# ── Reply-клавиатуры ────────────────────────────────────────────────────


def build_menu_keyboard(group_id: str) -> ReplyKeyboardMarkup:
    """Динамическое меню: кнопки категорий активной группы + служебные."""
    categories = gm.get_group_categories(group_id)
    rows: list[list[KeyboardButton]] = []
    for cat in categories:
        rows.append([KeyboardButton(text=cat.name)])
    rows.append([
        KeyboardButton(text="🔍 Поиск"),
        KeyboardButton(text="🗂 Категории"),
    ])
    rows.append([KeyboardButton(text="👥 Группы")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ── Inline-клавиатуры для рецептов ──────────────────────────────────────


# Границы числа порций кнопками пересчёта
PORTIONS_MIN = 1
PORTIONS_MAX = 20


def _portions_label(n: int) -> str:
    """Название кнопки с текущим числом порций (с плюрализацией)."""
    if n % 10 == 1 and n % 100 != 11:
        word = "порция"
    elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        word = "порции"
    else:
        word = "порций"
    return f"{n} {word}"


def add_portions_row(
    builder: InlineKeyboardBuilder,
    rk,
    base_portions: int,
    current_portions: int | None = None,
) -> None:
    """Добавляет в ``builder`` ряд пересчёта порций ``[➖][N порций][➕]``.

    No-op при ``base_portions <= 0`` (не на что делить). Кнопки на границах
    диапазона ``PORTIONS_MIN..PORTIONS_MAX`` скрываются.
    """
    if base_portions <= 0:
        return
    current = base_portions if current_portions is None else current_portions
    row: list[InlineKeyboardButton] = []
    if current > PORTIONS_MIN:
        row.append(InlineKeyboardButton(
            text="➖", callback_data=f"psc:{rk}:{current - 1}"))
    row.append(InlineKeyboardButton(
        text=_portions_label(current), callback_data="pnoop"))
    if current < PORTIONS_MAX:
        row.append(InlineKeyboardButton(
            text="➕", callback_data=f"psc:{rk}:{current + 1}"))
    builder.row(*row)


def recipe_keyboard(
    recipe_id: int,
    group_id: str | None = None,
    *,
    source_url: str | None = None,
    include_random: bool = False,
    base_portions: int = 0,
    current_portions: int | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура под рецептом.

    base_portions: базовое число порций рецепта (из LLM). При >0 под основными
        кнопками добавляется ряд пересчёта порций ``[➖][N порций][➕]``.
    current_portions: текущее выбранное число порций (для кнопок пересчёта);
        ``None`` означает первичный показ (``current = base_portions``).
    """
    rk = cache.put_recipe(recipe_id, group_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{rk}")

    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    if include_random:
        builder.button(text="🎲 Другой рецепт", callback_data="rnd")

    if source_url and include_random:
        builder.adjust(3, 1)
    elif source_url:
        builder.adjust(2, 1)
    elif include_random:
        builder.adjust(2, 1)
    else:
        builder.adjust(2)

    add_portions_row(builder, rk, base_portions, current_portions)

    return builder.as_markup()


def confirm_delete_keyboard(rk) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления рецепта (Да / Нет)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Да", callback_data=f"delok:{rk}")
    builder.button(text="Нет", callback_data=f"delcn:{rk}")
    builder.adjust(2)
    return builder.as_markup()


def duplicate_keyboard(recipe_id: int, recipe: object = None) -> InlineKeyboardMarkup:
    """Клавиатура при обнаружении дубликата рецепта."""
    rk = cache.put({"recipe_id": recipe_id, "recipe": recipe})

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Перезаписать", callback_data=f"ow:{rk}")
    builder.button(text="📝 Сохранить как новый", callback_data=f"sn:{rk}")
    builder.adjust(2)

    return builder.as_markup


def category_select_keyboard(
    group_id: str,
    rk,
) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории для переноса рецепта."""
    categories = gm.get_group_categories(group_id)

    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(
            text=cat.name,
            callback_data=f"mov:{cat.category_id}:{rk}",
        )
    builder.button(text="🔙 Отмена", callback_data=f"delcn:{rk}")
    builder.adjust(1)

    return builder.as_markup


def search_pagination_keyboard(
    cache_key: str,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    """Клавиатура пагинации для результатов поиска."""
    builder = InlineKeyboardBuilder()

    has_prev = page > 0
    page_size = 5
    has_next = (page + 1) * page_size < total

    if has_prev and has_next:
        builder.button(text="« Назад", callback_data=f"spage:{cache_key}:{page - 1}")
        builder.button(text="Вперед »", callback_data=f"spage:{cache_key}:{page + 1}")
        builder.adjust(2)
    elif has_prev:
        builder.button(text="« Назад", callback_data=f"spage:{cache_key}:{page - 1}")
        builder.adjust(1)
    elif has_next:
        builder.button(text="Вперед »", callback_data=f"spage:{cache_key}:{page + 1}")
        builder.adjust(1)

    return builder.as_markup()


# ── Inline-клавиатуры для групп ─────────────────────────────────────────


def group_list_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура со списком групп пользователя"""
    groups = gm.get_user_groups(user_id)
    active_group = gm.get_user_active_group(user_id)

    builder = InlineKeyboardBuilder()
    for group in groups:
        marker = " ✅" if group.group_id == active_group else ""
        builder.button(
            text=f"{'📁' if group.is_personal else '👥'} {group.name}{marker}",
            callback_data=f"grp:{group.group_id}",
        )

    builder.button(text="➕ Создать группу", callback_data="grp_new")
    builder.button(text="🔗 Вступить по коду", callback_data="grp_join")
    builder.button(text="🔙 Назад", callback_data="grp_back")
    builder.adjust(1)

    return builder.as_markup()


def group_detail_keyboard(
    group_id: str, user_id: int
) -> InlineKeyboardMarkup | None:
    """Клавиатура управления конкретной группой"""
    group = gm.get_group(group_id)
    if not group:
        return None

    builder = InlineKeyboardBuilder()

    active_group = gm.get_user_active_group(user_id)
    if group_id != active_group:
        builder.button(text="✅ Переключиться", callback_data=f"grp_sw:{group_id}")

    if group.owner_id == user_id:
        builder.button(text="🔗 Получить инвайт-код", callback_data=f"grp_inv:{group_id}")
        builder.button(text="✏️ Переименовать", callback_data=f"grp_rn:{group_id}")

    if not group.is_personal and group.owner_id != user_id:
        builder.button(text="🚪 Покинуть группу", callback_data=f"grp_lv:{group_id}")

    builder.button(text="🔙 К списку групп", callback_data="grp_list")
    builder.adjust(1)

    return builder.as_markup()


def format_group_list_text(user_id: int) -> str:
    """Форматирует текст списка групп для отправки в чат"""
    groups = gm.get_user_groups(user_id)
    active_group = gm.get_group(gm.get_user_active_group(user_id))

    lines = ["👥 **Ваши группы:**\n"]
    for g in groups:
        marker = " ✅ (активна)" if g.group_id == active_group.group_id else ""
        owner_tag = " (владелец)" if g.owner_id == user_id else ""
        member_count = len(g.members)
        lines.append(
            f"{'📁' if g.is_personal else '👥'} **{g.name}**{marker}{owner_tag} — {member_count} чел."
        )

    return "\n".join(lines)

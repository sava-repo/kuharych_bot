"""Общие функции построения клавиатур для Telegram-бота"""

from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import services.cache as cache
import services.group_manager as gm
from constants import (
    VALID_CATEGORIES,
    category_to_code,
)


# ── Reply-клавиатуры ────────────────────────────────────────────────────

MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌅 Завтрак")],
        [KeyboardButton(text="🍽 Основное блюдо")],
        [KeyboardButton(text="🍰 Десерт")],
        [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="👥 Группы")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


# ── Inline-клавиатуры для рецептов ──────────────────────────────────────


def recipe_keyboard(
    category: str,
    slug: str,
    *,
    group_id: str | None = None,
    source_url: str | None = None,
    include_random: bool = False,
    random_callback: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Клавиатура под рецептом.
    """
    rk = cache.put_recipe(category, slug)
    cc = category_to_code(category)

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Перенести", callback_data=f"rcat:{cc}:{rk}")

    if source_url:
        builder.button(text="▶️ Посмотреть", url=source_url)

    if include_random:
        rnd_cb = random_callback or f"rnd:{cc}"
        builder.button(text="🎲 Другой рецепт", callback_data=rnd_cb)

    if source_url and include_random:
        builder.adjust(3, 1)
    elif source_url:
        builder.adjust(2, 1)
    elif include_random:
        builder.adjust(2, 1)
    else:
        builder.adjust(2)

    return builder.as_markup()


def duplicate_keyboard(
    category: str,
    slug: str,
    recipe: object = None,
) -> InlineKeyboardMarkup:
    """
    Клавиатура при обнаружении дубликата рецепта.
    """
    rk = cache.put({
        "category": category,
        "slug": slug,
        "recipe": recipe,
    })
    cc = category_to_code(category)

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Перезаписать", callback_data=f"ow:{cc}:{rk}")
    builder.button(text="📝 Сохранить как новый", callback_data=f"sn:{cc}:{rk}")
    builder.adjust(2)

    return builder.as_markup()


def category_select_keyboard(
    current_category: str,
    rk,
    prefix: str = "mov",
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора категории (для перемещения рецепта).
    """
    current_cc = category_to_code(current_category)

    builder = InlineKeyboardBuilder()
    for cat in VALID_CATEGORIES:
        if cat != current_category:
            cc = category_to_code(cat)
            builder.button(
                text=cat.capitalize(),
                callback_data=f"{prefix}:{cc}:{current_cc}:{rk}",
            )
    builder.adjust(1)

    return builder.as_markup()


def search_pagination_keyboard(
    cache_key: str,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    """
    Клавиатура пагинации для результатов поиска.

    [« Назад] показывается только если page > 0.
    [Вперед »] показывается только если есть ещё результаты.
    """
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

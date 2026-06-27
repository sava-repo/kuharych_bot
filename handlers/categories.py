"""Управление категориями активной группы: добавить / переименовать / удалить."""

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import services.group_manager as gm
from exceptions import CategoryError
from handlers.keyboards import build_menu_keyboard

logger = logging.getLogger(__name__)

router = Router()


class CategoryStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_rename = State()


# ── Список категорий ───────────────────────────────────────────────────

@router.message(F.text == "🗂 Категории")
async def handle_categories_menu(message: Message) -> None:
    await message.answer(
        "🗂 Управление категориями:",
        reply_markup=_categories_keyboard(message.from_user.id),
    )


@router.callback_query(F.data == "cat_list")
async def handle_cat_list(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🗂 Управление категориями:",
        reply_markup=_categories_keyboard(callback.from_user.id),
    )


def _categories_keyboard(user_id: int) -> InlineKeyboardBuilder:
    group_id = gm.get_user_active_group(user_id)
    group = gm.get_group(group_id)
    group_name = group.name if group else "—"
    categories = gm.get_group_categories(group_id)

    builder = InlineKeyboardBuilder()
    for cat in categories:
        marker = " (по умолчанию)" if cat.is_default else ""
        builder.button(
            text=f"{cat.name}{marker}",
            callback_data=f"cat_view:{cat.category_id}",
        )
    builder.button(text="➕ Добавить категорию", callback_data="cat_add")
    builder.button(text="🔙 В меню", callback_data="cat_close")
    builder.adjust(1)
    return builder.as_markup()


# ── Детали категории ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat_view:"))
async def handle_cat_view(callback: CallbackQuery) -> None:
    category_id = int(callback.data.split(":", 1)[1])
    cat = gm.get_category_by_id(category_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Переименовать", callback_data=f"cat_rn:{category_id}")
    if not cat.is_default:
        builder.button(text="🗑 Удалить", callback_data=f"cat_del:{category_id}")
    builder.button(text="🔙 К списку", callback_data="cat_list")
    builder.adjust(1)

    default_tag = " (категория по умолчанию, неудаляемая)" if cat.is_default else ""
    await callback.message.edit_text(
        f"📂 Категория «{cat.name}»{default_tag}",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


# ── Добавление ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "cat_add")
async def handle_cat_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("📝 Введите название новой категории (1–50 символов):")
    await state.set_state(CategoryStates.waiting_for_name)
    await callback.answer()


@router.message(CategoryStates.waiting_for_name)
async def handle_cat_name_entered(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    group_id = gm.get_user_active_group(message.from_user.id)

    try:
        gm.create_category(group_id, name)
    except CategoryError as e:
        await message.answer(f"❌ {e}\n\nПопробуйте ещё раз:")
        return

    await state.clear()
    await message.answer(
        f"✅ Категория «{name}» добавлена",
        reply_markup=_categories_keyboard(message.from_user.id),
    )


# ── Переименование ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat_rn:"))
async def handle_cat_rename(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":", 1)[1])
    cat = gm.get_category_by_id(category_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    await callback.message.edit_text(f"✏️ Введите новое название для «{cat.name}»:")
    await state.set_state(CategoryStates.waiting_for_rename)
    await state.update_data(category_id=category_id)
    await callback.answer()


@router.message(CategoryStates.waiting_for_rename)
async def handle_cat_rename_entered(message: Message, state: FSMContext) -> None:
    new_name = message.text.strip() if message.text else ""
    data = await state.get_data()
    category_id = data.get("category_id")
    group_id = gm.get_user_active_group(message.from_user.id)

    if category_id is None:
        await state.clear()
        await message.answer("❌ Сессия устарела. Откройте категории заново.")
        return

    try:
        gm.rename_category(group_id, category_id, new_name)
    except CategoryError as e:
        await message.answer(f"❌ {e}\n\nПопробуйте ещё раз:")
        return

    await state.clear()
    await message.answer(
        f"✅ Категория переименована в «{new_name}»",
        reply_markup=_categories_keyboard(message.from_user.id),
    )


# ── Удаление ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat_del:") & ~F.data.startswith("cat_delok:"))
async def handle_cat_delete(callback: CallbackQuery) -> None:
    category_id = int(callback.data.split(":", 1)[1])
    cat = gm.get_category_by_id(category_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    if cat.is_default:
        await callback.answer("Категорию по умолчанию нельзя удалить", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=f"cat_delok:{category_id}")
    builder.button(text="Отмена", callback_data=f"cat_view:{category_id}")
    builder.adjust(2)

    await callback.message.edit_text(
        f"🗑 Удалить категорию «{cat.name}»?\n\n"
        f"Рецепты из неё будут перенесены в категорию по умолчанию.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_delok:"))
async def handle_cat_delete_confirm(callback: CallbackQuery) -> None:
    category_id = int(callback.data.split(":", 1)[1])
    group_id = gm.get_user_active_group(callback.from_user.id)
    cat = gm.get_category_by_id(category_id)
    name = cat.name if cat else "—"

    try:
        gm.delete_category(group_id, category_id)
    except CategoryError as e:
        await callback.answer(str(e), show_alert=True)
        return

    await callback.message.edit_text(
        f"🗑 Категория «{name}» удалена",
        reply_markup=_categories_keyboard(callback.from_user.id),
    )


# ── Закрытие меню категорий ────────────────────────────────────────────

@router.callback_query(F.data == "cat_close")
async def handle_cat_close(callback: CallbackQuery) -> None:
    """Закрывает меню категорий и обновляет reply-клавиатуру меню."""
    group_id = gm.get_user_active_group(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        "↩️ Возврат в меню",
        reply_markup=build_menu_keyboard(group_id),
    )
    await callback.answer()

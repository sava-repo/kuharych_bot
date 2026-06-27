"""Обработка кнопок управления группами"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import services.group_manager as gm
from handlers.keyboards import build_menu_keyboard

logger = logging.getLogger(__name__)

router = Router()


# ── FSM состояния ─────────────────────────────────────────────────────

class GroupStates(StatesGroup):
    waiting_for_group_name = State()
    waiting_for_invite_code = State()
    waiting_for_rename = State()


# ── Утилиты ───────────────────────────────────────────────────────────

def _group_list_keyboard(user_id: int) -> dict:
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


def _group_detail_keyboard(group_id: str, user_id: int) -> dict:
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


# ── Кнопка меню «Группы» ────────────────────────────────────────────

@router.message(F.text == "👥 Группы")
async def handle_my_groups(message: Message) -> None:
    """Показывает список групп пользователя"""
    user_id = message.from_user.id
    groups = gm.get_user_groups(user_id)
    active_group = gm.get_group(gm.get_user_active_group(user_id))

    text = "👥 **Ваши группы:**\n\n"
    for g in groups:
        marker = " ✅ (активна)" if g.group_id == active_group.group_id else ""
        owner_tag = " (владелец)" if g.owner_id == user_id else ""
        member_count = len(g.members)
        text += f"{'📁' if g.is_personal else '👥'} **{g.name}**{marker}{owner_tag} — {member_count} чел.\n"

    await message.answer(
        text,
        reply_markup=_group_list_keyboard(user_id),
        parse_mode="Markdown",
    )


# ── Callback: выбор группы из списка ──────────────────────────────────

@router.callback_query(F.data == "grp_list")
async def handle_grp_list(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    groups = gm.get_user_groups(user_id)
    active_group = gm.get_group(gm.get_user_active_group(user_id))

    text = "👥 **Ваши группы:**\n\n"
    for g in groups:
        marker = " ✅ (активна)" if g.group_id == active_group.group_id else ""
        owner_tag = " (владелец)" if g.owner_id == user_id else ""
        member_count = len(g.members)
        text += f"{'📁' if g.is_personal else '👥'} **{g.name}**{marker}{owner_tag} — {member_count} чел.\n"

    await callback.message.edit_text(
        text,
        reply_markup=_group_list_keyboard(user_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("grp:") & ~F.data.startswith("grp_:"))
async def handle_grp_select(callback: CallbackQuery) -> None:
    """Показывает детали группы"""
    group_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    group = gm.get_group(group_id)
    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        return

    is_active = group_id == gm.get_user_active_group(user_id)
    is_owner = group.owner_id == user_id

    text = f"{'📁' if group.is_personal else '👥'} **{group.name}**\n\n"
    text += f"{'✅ Активна' if is_active else 'Неактивна'}\n"
    text += f"Участников: {len(group.members)}\n"
    if group.invite_code and is_owner:
        text += f"Инвайт-код: `{group.invite_code}`\n"

    kb = _group_detail_keyboard(group_id, user_id)
    if kb is None:
        await callback.answer("Группа не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode="Markdown",
    )


# ── Переключение активной группы ──────────────────────────────────────

@router.callback_query(F.data.startswith("grp_sw:"))
async def handle_grp_switch(callback: CallbackQuery) -> None:
    """Переключает активную группу"""
    group_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    if gm.set_user_active_group(user_id, group_id):
        group = gm.get_group(group_id)
        await callback.answer(f"Переключено на «{group.name}»")
        # Обновляем reply-клавиатуру меню (категории зависят от группы)
        await callback.message.answer(
            f"📂 Активная группа: «{group.name}»",
            reply_markup=build_menu_keyboard(group_id),
        )
        # Обновляем детали
        await handle_grp_select(callback)
    else:
        await callback.answer("Не удалось переключиться", show_alert=True)


# ── Создание новой группы ─────────────────────────────────────────────

@router.callback_query(F.data == "grp_new")
async def handle_grp_new(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрашивает название для новой группы"""
    await callback.message.edit_text(
        "📝 Введите название для новой группы:"
    )
    await state.set_state(GroupStates.waiting_for_group_name)
    await callback.answer()


@router.message(GroupStates.waiting_for_group_name)
async def handle_group_name_entered(message: Message, state: FSMContext) -> None:
    """Создаёт группу с введённым названием"""
    name = message.text.strip()
    if not name or len(name) > 50:
        await message.answer("❌ Название должно быть от 1 до 50 символов. Попробуйте ещё раз:")
        return

    group = gm.create_custom_group(name, message.from_user.id)
    gm.set_user_active_group(message.from_user.id, group.group_id)

    await message.answer(
        f"✅ Группа «{group.name}» создана и сделана активной!",
        reply_markup=build_menu_keyboard(group.group_id),
    )
    await state.clear()


# ── Вступление по инвайт-коду ────────────────────────────────────────

@router.callback_query(F.data == "grp_join")
async def handle_grp_join(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрашивает инвайт-код"""
    await callback.message.edit_text(
        "🔗 Введите инвайт-код группы:"
    )
    await state.set_state(GroupStates.waiting_for_invite_code)
    await callback.answer()


@router.message(GroupStates.waiting_for_invite_code)
async def handle_invite_code_entered(message: Message, state: FSMContext) -> None:
    """Вступает в группу по инвайт-коду"""
    code = message.text.strip()
    if not code:
        await state.clear()
        await message.answer("❌ Пустой код.")
        return

    await state.clear()

    group = gm.join_group_by_code(code, message.from_user.id)
    if group:
        await message.answer(
            f"✅ Вы вступили в группу «{group.name}»!",
            reply_markup=_group_list_keyboard(message.from_user.id),
        )
    else:
        await message.answer(
            "❌ Группа с таким кодом не найдена.",
            reply_markup=_group_list_keyboard(message.from_user.id),
        )


# ── Получение инвайт-кода ────────────────────────────────────────────

@router.callback_query(F.data.startswith("grp_inv:"))
async def handle_grp_invite(callback: CallbackQuery) -> None:
    """Генерирует и показывает инвайт-код"""
    group_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    code = gm.generate_invite_code(group_id, user_id)
    if code:
        group = gm.get_group(group_id)
        group_name = group.name if group else "Неизвестная"
        await callback.answer()
        await callback.message.answer(
            f"🔗 Инвайт-код для группы «{group_name}»:\n\n`{code}`",
            parse_mode="Markdown",
        )
    else:
        await callback.answer("Нет прав для создания инвайт-кода", show_alert=True)


# ── Переименование группы ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("grp_rn:"))
async def handle_grp_rename(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрашивает новое название группы"""
    group_id = callback.data.split(":", 1)[1]

    await callback.message.edit_text("✏️ Введите новое название группы:")
    await state.set_state(GroupStates.waiting_for_rename)
    await state.update_data(rename_group_id=group_id)
    await callback.answer()


@router.message(GroupStates.waiting_for_rename)
async def handle_rename_entered(message: Message, state: FSMContext) -> None:
    """Переименовывает группу"""
    data = await state.get_data()
    group_id = data.get("rename_group_id", "")
    new_name = message.text.strip()

    if not new_name or len(new_name) > 50:
        await message.answer("❌ Название должно быть от 1 до 50 символов. Попробуйте ещё раз:")
        return

    if gm.rename_group(group_id, message.from_user.id, new_name):
        await message.answer(
            f"✅ Группа переименована в «{new_name}»",
            reply_markup=_group_list_keyboard(message.from_user.id),
        )
    else:
        await message.answer("❌ Не удалось переименовать. Нет прав.")

    await state.clear()


# ── Выход из группы ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("grp_lv:"))
async def handle_grp_leave(callback: CallbackQuery) -> None:
    """Пользователь покидает группу"""
    group_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    group = gm.get_group(group_id)
    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        return

    if gm.leave_group(group_id, user_id):
        await callback.message.edit_text(
            f"✅ Вы покинули группу «{group.name}»",
            reply_markup=_group_list_keyboard(user_id),
        )
    else:
        await callback.answer("Не удалось покинуть группу", show_alert=True)


# ── Назад ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "grp_back")
async def handle_grp_back(callback: CallbackQuery) -> None:
    """Закрывает меню групп"""
    await callback.message.delete()
    await callback.answer()
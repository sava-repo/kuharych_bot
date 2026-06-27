"""Обработка inline/callback кнопок"""

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

import services.group_manager as gm
import services.cache as cache
from models.recipe import Recipe
from handlers.keyboards import (
    recipe_keyboard,
    category_select_keyboard,
    confirm_delete_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()


def _parse_callback(callback: CallbackQuery, expected_parts: int) -> tuple[str, ...] | None:
    """Парсит callback_data, возвращает parts или None при ошибке."""
    parts = callback.data.split(":")
    if len(parts) != expected_parts:
        return None
    return parts[1:]


def _cached(callback: CallbackQuery, parts_count: int) -> dict | None:
    """Парсит callback и получает данные рецепта из кэша."""
    parts = _parse_callback(callback, parts_count)
    if parts is None:
        return None
    rk = parts[-1]
    return cache.get(rk)


async def _restore_recipe_view(callback: CallbackQuery, recipe_id: int, group_id: str) -> None:
    """Восстанавливает сообщение с рецептом и стандартной клавиатурой."""
    recipe_data = gm.get_recipe(recipe_id)
    if not recipe_data:
        await callback.message.edit_text("❌ Рецепт не найден")
        return

    recipe = Recipe.from_markdown(recipe_data["content_md"], recipe_data["source"])
    category = gm.get_group_recipe_category(group_id, recipe_id)
    category_name = category.name if category else None
    source_url = gm.find_source_by_recipe_id(recipe_id)

    await callback.message.edit_text(
        recipe.format_message(category_name),
        reply_markup=recipe_keyboard(recipe_id, group_id, source_url=source_url),
    )


# ── Удаление рецепта ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del:"))
async def handle_delete(callback: CallbackQuery) -> None:
    """Шаг 1: показ диалога подтверждения удаления рецепта"""
    cached = _cached(callback, 2)
    if not cached:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    recipe_id = cached["recipe_id"]
    recipe_data = gm.get_recipe(recipe_id)
    name = (recipe_data["title"] if recipe_data else None) or f"#{recipe_id}"

    await callback.answer()
    await callback.message.edit_text(
        f"Вы действительно хотите удалить рецепт «{name}»?",
        reply_markup=confirm_delete_keyboard(_rk_from(callback)),
    )


@router.callback_query(F.data.startswith("delok:"))
async def handle_delete_confirm(callback: CallbackQuery) -> None:
    """Шаг 2 (подтверждение): реальное удаление рецепта из текущей группы"""
    user_id = callback.from_user.id
    cached = _cached(callback, 2)
    if not cached:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    recipe_id = cached["recipe_id"]
    group_id = cached.get("group_id") or gm.get_user_active_group(user_id)

    await callback.answer("Удаляю...")

    try:
        removed = gm.remove_recipe_from_group(group_id, recipe_id)
        if not removed:
            await callback.message.edit_text("❌ Рецепт не найден в вашей группе")
            return

        if not gm.recipe_exists_in_any_group(recipe_id):
            gm.delete_recipe(recipe_id)
            logger.info("Recipe fully deleted from DB: recipe_id=%s", recipe_id)

        await callback.message.edit_text(f"🗑 Рецепт удалён из коллекции")
        logger.info("Recipe removed from group %s: recipe_id=%s", group_id, recipe_id)

    except Exception as e:
        logger.error("Delete error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось удалить рецепт. Попробуйте позже")


@router.callback_query(F.data.startswith("delcn:"))
async def handle_delete_cancel(callback: CallbackQuery) -> None:
    """Шаг 2 (отмена): возврат к просмотру рецепта"""
    cached = _cached(callback, 2)
    if not cached:
        await callback.answer("Данные устарели", show_alert=True)
        return

    recipe_id = cached["recipe_id"]
    group_id = cached.get("group_id") or gm.get_user_active_group(callback.from_user.id)

    await callback.answer()
    await _restore_recipe_view(callback, recipe_id, group_id)


# ── Перезапись рецепта ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ow:"))
async def handle_overwrite(callback: CallbackQuery) -> None:
    """Перезапись существующего рецепта новым содержимым"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)
    cached = _cached(callback, 2)
    if not cached:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    recipe = cached.get("recipe")
    if not recipe:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    await callback.answer("Перезаписываю...")

    try:
        recipe_id = gm.overwrite_recipe(recipe)

        await callback.message.edit_text(
            f"✅ Рецепт «{recipe.title}» перезаписан",
            reply_markup=recipe_keyboard(recipe_id, group_id),
        )
        logger.info("Recipe overwritten via button: recipe_id=%s", recipe_id)

    except Exception as e:
        logger.error("Overwrite error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось перезаписать рецепт. Попробуйте позже")


# ── Сохранить как новый ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sn:"))
async def handle_save_new(callback: CallbackQuery) -> None:
    """Сохранение рецепта с новым названием (копия)"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)
    cached = _cached(callback, 2)
    if not cached:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    recipe = cached.get("recipe")
    if not recipe:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    await callback.answer("Сохраняю как новый...")

    try:
        recipe_id, new_slug = gm.save_recipe_as_new(recipe)
        category_id = gm.get_default_category_id(group_id)
        gm.add_recipe_to_group(group_id, recipe_id, category_id, user_id)

        await callback.message.edit_text(
            f"✅ Рецепт сохранён как «{new_slug}»",
            reply_markup=recipe_keyboard(recipe_id, group_id),
        )
        logger.info("Recipe saved as new via button: recipe_id=%s", recipe_id)

    except Exception as e:
        logger.error("Save new error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось сохранить рецепт. Попробуйте позже")


# ── Смена категории (шаг 1: выбор) ─────────────────────────────────────

@router.callback_query(F.data.startswith("rcat:"))
async def handle_recat(callback: CallbackQuery) -> None:
    """Выбор новой категории для рецепта"""
    cached = _cached(callback, 2)
    if not cached:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    recipe_id = cached["recipe_id"]
    recipe_data = gm.get_recipe(recipe_id)
    name = (recipe_data["title"] if recipe_data else None) or f"#{recipe_id}"

    group_id = cached.get("group_id") or gm.get_user_active_group(callback.from_user.id)

    await callback.message.edit_text(
        f"📂 Выберите новую категорию для «{name}»:",
        reply_markup=category_select_keyboard(group_id, _rk_from(callback)),
    )


# ── Перемещение рецепта (шаг 2: выполнение) ────────────────────────────

@router.callback_query(F.data.startswith("mov:"))
async def handle_move(callback: CallbackQuery) -> None:
    """Перемещение рецепта в другую категорию (в рамках текущей группы)"""
    parts = _parse_callback(callback, 3)
    if not parts:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    new_category_id_str, rk = parts
    new_category_id = int(new_category_id_str)
    cached = cache.get(rk)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    recipe_id = cached["recipe_id"]
    group_id = cached.get("group_id") or gm.get_user_active_group(callback.from_user.id)

    new_category = gm.get_category_by_id(new_category_id)
    new_name = new_category.name if new_category else "—"
    await callback.answer(f"Перемещаю в «{new_name}»...")

    try:
        if not gm.move_recipe_in_group(group_id, recipe_id, new_category_id):
            await callback.message.edit_text("❌ Не удалось переместить рецепт")
            return

        cache.update(rk, {"recipe_id": recipe_id, "group_id": group_id})

        await callback.message.edit_text(
            f"✅ Рецепт перемещён в «{new_name}»",
            reply_markup=recipe_keyboard(recipe_id, group_id),
        )
        logger.info("Recipe moved: recipe_id=%s -> category_id=%s (group %s)",
                    recipe_id, new_category_id, group_id)

    except Exception as e:
        logger.error("Move error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось переместить рецепт. Попробуйте позже")


def _rk_from(callback: CallbackQuery) -> str:
    """Излекает rk (последний элемент) из callback_data."""
    return callback.data.split(":")[-1]

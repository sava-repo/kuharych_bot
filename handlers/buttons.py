"""Обработка inline/callback кнопок"""

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

import services.group_manager as gm
import services.cache as cache
from constants import code_to_category
from handlers.keyboards import (
    recipe_keyboard,
    category_select_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()


def _parse_callback(callback: CallbackQuery, expected_parts: int) -> tuple[str, ...] | None:
    """Парсит callback_data, возвращает parts или None при ошибке."""
    parts = callback.data.split(":")
    if len(parts) != expected_parts:
        return None
    return parts[1:]


def _resolve_cached(callback: CallbackQuery, parts_count: int) -> tuple[tuple[str, ...], dict] | None:
    """Парсит callback и получает данные из кэша. Возвращает (parts, cached) или None."""
    parts = _parse_callback(callback, parts_count)
    if parts is None:
        return None
    rk = parts[-1]
    cached = cache.get(rk)
    if not cached:
        return None
    return parts, cached


# ── Удаление рецепта ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del:"))
async def handle_delete(callback: CallbackQuery) -> None:
    """Удаление рецепта из текущей группы"""
    user_id = callback.from_user.id
    result = _resolve_cached(callback, 3)
    if not result:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    (_, rk), cached = result
    category = cached["category"]
    slug = cached["slug"]
    group_id = cached.get("group_id") or gm.get_user_active_group(user_id)

    await callback.answer("Удаляю...")

    try:
        removed = gm.remove_recipe_from_group(group_id, category, slug)
        if not removed:
            await callback.message.edit_text("❌ Рецепт не найден в вашей группе")
            return

        if not gm.recipe_exists_in_any_group(category, slug):
            gm.delete_recipe(category, slug)
            logger.info("Recipe fully deleted from DB: %s/%s", category, slug)

        await callback.message.edit_text(f"🗑 Рецепт «{slug}» удалён из коллекции")
        logger.info("Recipe removed from group %s: %s/%s", group_id, category, slug)

    except Exception as e:
        logger.error("Delete error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось удалить рецепт. Попробуйте позже")


# ── Перезапись рецепта ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ow:"))
async def handle_overwrite(callback: CallbackQuery) -> None:
    """Перезапись существующего рецепта новым содержимым"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)
    result = _resolve_cached(callback, 3)
    if not result:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    (_, rk), cached = result
    recipe = cached.get("recipe")
    if not recipe:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    await callback.answer("Перезаписываю...")

    try:
        gm.overwrite_recipe(recipe)

        await callback.message.edit_text(
            f"✅ Рецепт «{recipe.title}» перезаписан",
            reply_markup=recipe_keyboard(recipe.category, recipe.slug),
        )
        logger.info("Recipe overwritten via button: %s/%s", recipe.category, recipe.slug)

    except Exception as e:
        logger.error("Overwrite error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось перезаписать рецепт. Попробуйте позже")


# ── Сохранить как новый ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sn:"))
async def handle_save_new(callback: CallbackQuery) -> None:
    """Сохранение рецепта с новым названием (копия)"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)
    result = _resolve_cached(callback, 3)
    if not result:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    (_, rk), cached = result
    recipe = cached.get("recipe")
    if not recipe:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    await callback.answer("Сохраняю как новый...")

    try:
        new_slug = gm.save_recipe_as_new(recipe)

        gm.add_recipe_to_group(group_id, recipe.category, new_slug)

        await callback.message.edit_text(
            f"✅ Рецепт сохранён как «{new_slug}»",
            reply_markup=recipe_keyboard(recipe.category, new_slug, group_id=group_id),
        )
        logger.info("Recipe saved as new via button: %s/%s", recipe.category, new_slug)

    except Exception as e:
        logger.error("Save new error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось сохранить рецепт. Попробуйте позже")


# ── Смена категории (шаг 1: выбор) ─────────────────────────────────────

@router.callback_query(F.data.startswith("rcat:"))
async def handle_recat(callback: CallbackQuery) -> None:
    """Выбор новой категории для рецепта"""
    result = _resolve_cached(callback, 3)
    if not result:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    (_, rk), cached = result
    category = cached["category"]
    slug = cached["slug"]

    await callback.message.edit_text(
        f"📂 Выберите новую категорию для «{slug}»:",
        reply_markup=category_select_keyboard(category, rk),
    )


# ── Перемещение рецепта (шаг 2: выполнение) ────────────────────────────

@router.callback_query(F.data.startswith("mov:"))
async def handle_move(callback: CallbackQuery) -> None:
    """Перемещение рецепта в другую категорию"""
    parts = _parse_callback(callback, 4)
    if not parts:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    new_cc, old_cc, rk = parts
    new_category = code_to_category(new_cc)
    old_category = code_to_category(old_cc)
    cached = cache.get(rk)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    slug = cached["slug"]

    await callback.answer(f"Перемещаю в «{new_category}»...")

    try:
        gm.move_recipe(old_category, slug, new_category)

        source_url = gm.find_source_by_slug(old_category, slug)
        if source_url:
            gm.register_source(source_url, new_category, slug)

        cache.update(rk, {"category": new_category, "slug": slug, "group_id": cached.get("group_id")})

        await callback.message.edit_text(
            f"✅ Рецепт «{slug}» перемещён в «{new_category}»",
            reply_markup=recipe_keyboard(new_category, slug),
        )
        logger.info("Recipe moved: %s/%s -> %s/%s", old_category, slug, new_category, slug)

    except Exception as e:
        logger.error("Move error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось переместить рецепт. Попробуйте позже")

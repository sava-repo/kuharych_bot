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
    PORTIONS_MIN,
    PORTIONS_MAX,
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


def _parse_ref(
    callback: CallbackQuery, expected_parts: int
) -> tuple[int, str] | None:
    """Парсит callback с payload рецепта, возвращает (recipe_id, group_id).

    payload кодируется как ``recipe_id:group_id`` и занимает два последних
    сегмента ``callback_data`` (del/delok/delcn/rcat/mov). Не обращается к
    кэшу — данные читаются прямо из кнопки, поэтому переживают рестарт.
    """
    parts = _parse_callback(callback, expected_parts)
    if parts is None:
        return None
    try:
        return int(parts[-2]), parts[-1]
    except (ValueError, IndexError):
        return None


async def _restore_recipe_view(
    callback: CallbackQuery,
    recipe_id: int,
    group_id: str,
    *,
    portions_override: int | None = None,
) -> None:
    """Восстанавливает сообщение с рецептом и стандартной клавиатурой.

    portions_override: выбранное число порций; при передаче ингредиенты
        пересчитываются, а клавиатура показывает его как текущее.
    """
    recipe_data = gm.get_recipe(recipe_id)
    if not recipe_data:
        await callback.message.edit_text("❌ Рецепт не найден")
        return

    recipe = Recipe.from_markdown(recipe_data["content_md"], recipe_data["source"])
    category = gm.get_group_recipe_category(group_id, recipe_id)
    category_name = category.name if category else None
    source_url = gm.find_source_by_recipe_id(recipe_id)

    await callback.message.edit_text(
        recipe.format_message(category_name, portions_override=portions_override),
        reply_markup=recipe_keyboard(
            recipe_id,
            group_id,
            source_url=source_url,
            base_portions=recipe.portions,
            current_portions=portions_override,
        ),
    )


# ── Удаление рецепта ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del:"))
async def handle_delete(callback: CallbackQuery) -> None:
    """Шаг 1: показ диалога подтверждения удаления рецепта"""
    ref = _parse_ref(callback, 3)
    if ref is None:
        await callback.answer("Данные устарели", show_alert=True)
        return

    recipe_id, group_id = ref
    recipe_data = gm.get_recipe(recipe_id)
    name = (recipe_data["title"] if recipe_data else None) or f"#{recipe_id}"

    await callback.answer()
    await callback.message.edit_text(
        f"Вы действительно хотите удалить рецепт «{name}»?",
        reply_markup=confirm_delete_keyboard(f"{recipe_id}:{group_id}"),
    )


@router.callback_query(F.data.startswith("delok:"))
async def handle_delete_confirm(callback: CallbackQuery) -> None:
    """Шаг 2 (подтверждение): реальное удаление рецепта из текущей группы"""
    ref = _parse_ref(callback, 3)
    if ref is None:
        await callback.answer("Данные устарели", show_alert=True)
        return

    recipe_id, group_id = ref

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
    ref = _parse_ref(callback, 3)
    if ref is None:
        await callback.answer("Данные устарели", show_alert=True)
        return

    recipe_id, group_id = ref

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
    ref = _parse_ref(callback, 3)
    if ref is None:
        await callback.answer("Данные устарели", show_alert=True)
        return

    recipe_id, group_id = ref
    recipe_data = gm.get_recipe(recipe_id)
    name = (recipe_data["title"] if recipe_data else None) or f"#{recipe_id}"

    await callback.message.edit_text(
        f"📂 Выберите новую категорию для «{name}»:",
        reply_markup=category_select_keyboard(group_id, f"{recipe_id}:{group_id}"),
    )


# ── Перемещение рецепта (шаг 2: выполнение) ────────────────────────────

@router.callback_query(F.data.startswith("mov:"))
async def handle_move(callback: CallbackQuery) -> None:
    """Перемещение рецепта в другую категорию (в рамках текущей группы)"""
    parts = _parse_callback(callback, 4)
    if parts is None:
        await callback.answer("Данные устарели", show_alert=True)
        return

    new_category_id_str, recipe_id_str, group_id = parts
    new_category_id = int(new_category_id_str)
    recipe_id = int(recipe_id_str)

    new_category = gm.get_category_by_id(new_category_id)
    new_name = new_category.name if new_category else "—"
    await callback.answer(f"Перемещаю в «{new_name}»...")

    try:
        if not gm.move_recipe_in_group(group_id, recipe_id, new_category_id):
            await callback.message.edit_text("❌ Не удалось переместить рецепт")
            return

        await callback.message.edit_text(
            f"✅ Рецепт перемещён в «{new_name}»",
            reply_markup=recipe_keyboard(recipe_id, group_id),
        )
        logger.info("Recipe moved: recipe_id=%s -> category_id=%s (group %s)",
                    recipe_id, new_category_id, group_id)

    except Exception as e:
        logger.error("Move error: %s", e, exc_info=True)
        await callback.message.edit_text("❌ Не удалось переместить рецепт. Попробуйте позже")


# ── Пересчёт порций ─────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("psc:"))
async def handle_portions_change(callback: CallbackQuery) -> None:
    """Кнопка пересчёта числа порций: масштабирует ингредиенты."""
    parts = _parse_callback(callback, 4)
    if parts is None:
        await callback.answer("Данные устарели", show_alert=True)
        return

    recipe_id_str, group_id, target_str = parts
    try:
        recipe_id = int(recipe_id_str)
        target = int(target_str)
    except ValueError:
        await callback.answer("Данные устарели", show_alert=True)
        return
    # Защита от подделанного callback_data
    target = max(PORTIONS_MIN, min(PORTIONS_MAX, target))

    await callback.answer()
    await _restore_recipe_view(callback, recipe_id, group_id, portions_override=target)


@router.callback_query(F.data == "pnoop")
async def handle_portions_noop(callback: CallbackQuery) -> None:
    """Центральная кнопка «N порций»: закрывает спиннер без действия."""
    await callback.answer()

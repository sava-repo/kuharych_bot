"""Обработка inline/callback кнопок"""

import base64
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import services.gramax as gramax
import services.group_manager as gm

logger = logging.getLogger(__name__)

router = Router()

VALID_CATEGORIES = ["завтрак", "основное блюдо", "десерт"]


def _cc(category: str) -> str:
    """Короткий код категории"""
    return config.CATEGORY_TO_CODE.get(category, "o")


def _cat(code: str) -> str:
    """Категория по короткому коду"""
    return config.CODE_TO_CATEGORY.get(code, "основное блюдо")


def _resolve(rk: str) -> dict | None:
    """Получает данные рецепта из кэша по ключу"""
    return config._callback_cache.get(rk)


def _recipe_kb(category: str, rk: str) -> dict:
    """Клавиатура под рецептом — возвращает InlineKeyboardMarkup"""
    cc = _cc(category)
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}")
    builder.adjust(2)
    return builder.as_markup()


def _check_member(callback: CallbackQuery) -> bool:
    """Проверяет что пользователь является участником группы рецепта"""
    return True  # Все аутентифицированные пользователи бота имеют доступ


@router.callback_query(F.data.startswith("del:"))
async def handle_delete(callback: CallbackQuery) -> None:
    """Удаление рецепта из текущей группы"""
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc, rk = parts
    cached = _resolve(rk)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    category = cached["category"]
    slug = cached["slug"]
    group_id = cached.get("group_id") or gm.get_user_active_group(user_id)

    await callback.answer("Удаляю...")

    try:
        # Удаляем рецепт из группы
        removed = gm.remove_recipe_from_group(group_id, category, slug)

        if not removed:
            await callback.message.edit_text("❌ Рецепт не найден в вашей группе")
            return

        # Если рецепт больше ни в одной группе — удаляем из GitHub
        if not gm.recipe_exists_in_any_group(category, slug):
            try:
                await gramax.delete_recipe(category, slug)
                logger.info(f"Recipe fully deleted from GitHub: {category}/{slug}")
            except Exception as e:
                logger.warning(f"Failed to delete from GitHub (non-critical): {e}")

        await callback.message.edit_text(f"🗑 Рецепт «{slug}» удалён из коллекции")
        logger.info(f"Recipe removed from group {group_id}: {category}/{slug}")

    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Не удалось удалить рецепт. Попробуйте позже")


@router.callback_query(F.data.startswith("ow:"))
async def handle_overwrite(callback: CallbackQuery) -> None:
    """Перезапись существующего рецепта"""
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc, rk = parts
    cached = _resolve(rk)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    category = cached["category"]
    slug = cached["slug"]
    sha = cached.get("sha")
    if not sha:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    await callback.answer("Перезаписываю...")

    try:
        # Читаем текущий рецепт
        content = await gramax.get_recipe_content(category, f"{slug}.md")
        content_b64 = base64.b64encode(content.encode("utf-8")).decode()

        filepath = f"receipts/{category}/{slug}.md"
        url = gramax._api_url(filepath)

        resp = await gramax._github_request(
            "PUT",
            url,
            json={
                "message": f"Overwrite recipe: {slug}",
                "content": content_b64,
                "sha": sha,
            },
        )

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"GitHub API error: {resp.status_code}")

        await callback.message.edit_text(
            f"✅ Рецепт «{slug}» перезаписан",
            reply_markup=_recipe_kb(category, rk),
        )
        logger.info(f"Recipe overwritten via button: {category}/{slug}")

    except Exception as e:
        logger.error(f"Overwrite error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Не удалось перезаписать рецепт. Попробуйте позже")


@router.callback_query(F.data.startswith("sn:"))
async def handle_save_new(callback: CallbackQuery) -> None:
    """Сохранение рецепта с новым названием"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc, rk = parts
    cached = _resolve(rk)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    category = cached["category"]
    slug = cached["slug"]

    await callback.answer("Сохраняю как новый...")

    try:
        # Читаем текущий рецепт
        content = await gramax.get_recipe_content(category, f"{slug}.md")

        # Создаём новый файл с суффиксом -2
        new_slug = f"{slug}-2"
        new_filename = f"{new_slug}.md"
        content_b64 = base64.b64encode(content.encode("utf-8")).decode()

        filepath = f"receipts/{category}/{new_filename}"
        url = gramax._api_url(filepath)

        resp = await gramax._github_request(
            "PUT",
            url,
            json={
                "message": f"Add recipe (copy): {new_slug}",
                "content": content_b64,
            },
        )

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"GitHub API error: {resp.status_code}")

        # Добавляем новый рецепт в группу
        gm.add_recipe_to_group(group_id, category, new_slug)

        # Кэшируем новый slug
        new_rk = f"r{len(config._callback_cache)}"
        config._callback_cache[new_rk] = {"category": category, "slug": new_slug, "group_id": group_id}

        await callback.message.edit_text(
            f"✅ Рецепт сохранён как «{new_slug}»",
            reply_markup=_recipe_kb(category, new_rk),
        )
        logger.info(f"Recipe saved as new via button: {category}/{new_slug}")

    except Exception as e:
        logger.error(f"Save new error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Не удалось сохранить рецепт. Попробуйте позже")


@router.callback_query(F.data.startswith("rcat:"))
async def handle_recat(callback: CallbackQuery) -> None:
    """Выбор новой категории для рецепта"""
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc, rk = parts
    cached = _resolve(rk)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    category = cached["category"]
    slug = cached["slug"]

    # Клавиатура выбора новой категории
    builder = InlineKeyboardBuilder()
    for cat in VALID_CATEGORIES:
        if cat != category:
            builder.button(
                text=cat.capitalize(),
                callback_data=f"mov:{_cc(cat)}:{_cc(category)}:{rk}",
            )
    builder.adjust(1)

    await callback.message.edit_text(
        f"📂 Выберите новую категорию для «{slug}»:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("mov:"))
async def handle_move(callback: CallbackQuery) -> None:
    """Перемещение рецепта в другую категорию"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, new_cc, old_cc, rk = parts
    new_category = _cat(new_cc)
    old_category = _cat(old_cc)
    cached = _resolve(rk)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    slug = cached["slug"]

    await callback.answer(f"Перемещаю в «{new_category}»...")

    try:
        # Читаем текущий рецепт
        content = await gramax.get_recipe_content(old_category, f"{slug}.md")

        # Удаляем из старой категории в GitHub
        await gramax.delete_recipe(old_category, slug)

        # Сохраняем в новой категории
        content_b64 = base64.b64encode(content.encode("utf-8")).decode()
        filepath = f"receipts/{new_category}/{slug}.md"

        # Убедимся что категория существует
        await gramax._ensure_category_dir(new_category)

        url = gramax._api_url(filepath)

        resp = await gramax._github_request(
            "PUT",
            url,
            json={
                "message": f"Move recipe: {slug} from {old_category} to {new_category}",
                "content": content_b64,
            },
        )

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"GitHub API error: {resp.status_code}")

        # Обновляем связи в группе
        gm.remove_recipe_from_group(group_id, old_category, slug)
        gm.add_recipe_to_group(group_id, new_category, slug)

        # Обновляем кэш
        config._callback_cache[rk] = {"category": new_category, "slug": slug, "group_id": group_id}

        await callback.message.edit_text(
            f"✅ Рецепт «{slug}» перемещён в «{new_category}»",
            reply_markup=_recipe_kb(new_category, rk),
        )
        logger.info(f"Recipe moved: {old_category}/{slug} -> {new_category}/{slug}")

    except Exception as e:
        logger.error(f"Move error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Не удалось переместить рецепт. Попробуйте позже")
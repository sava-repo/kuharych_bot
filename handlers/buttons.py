"""Обработка inline/callback кнопок"""

import base64
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import services.gramax as gramax
import services.group_manager as gm
import services.cache as cache

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
    return cache.get(rk)


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
    """Перезапись существующего рецепта новым содержимым"""
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

    recipe = cached.get("recipe")
    if not recipe:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    sha = cached.get("sha")
    if not sha:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    await callback.answer("Перезаписываю...")

    try:
        # Перезаписываем новым рецептом
        await gramax.overwrite_recipe(recipe, sha)
        
        # Обновляем кэш с новым sha
        # Получаем новый sha из GitHub
        duplicate_info = await gramax.check_duplicate(recipe.category, recipe.slug)
        if duplicate_info:
            cache.update(rk, {
                "category": recipe.category,
                "slug": recipe.slug,
                "sha": duplicate_info["sha"],
                "recipe": recipe,
                "group_id": group_id,
            })

        await callback.message.edit_text(
            f"✅ Рецепт «{recipe.title}» перезаписан",
            reply_markup=_recipe_kb(recipe.category, rk),
        )
        logger.info(f"Recipe overwritten via button: {recipe.category}/{recipe.slug}")

    except Exception as e:
        logger.error(f"Overwrite error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Не удалось перезаписать рецепт. Попробуйте позже")


@router.callback_query(F.data.startswith("sn:"))
async def handle_save_new(callback: CallbackQuery) -> None:
    """Сохранение рецепта с новым названием (копия)"""
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

    recipe = cached.get("recipe")
    if not recipe:
        await callback.message.edit_text("❌ Данные устарели. Отправьте ссылку заново")
        return

    await callback.answer("Сохраняю как новый...")

    try:
        # Сохраняем копию рецепта с инкрементальным суффиксом
        filepath, suffix = await gramax.save_recipe_as_new(recipe)
        new_slug = f"{recipe.slug}-{suffix}"

        # Добавляем новый рецепт в группу
        gm.add_recipe_to_group(group_id, recipe.category, new_slug)

        # Кэшируем данные нового рецепта
        new_rk = cache.put({
            "category": recipe.category,
            "slug": new_slug,
            "group_id": group_id,
            "recipe": None  # Для сохранённой копии рецепт в кэше не нужен
        })

        await callback.message.edit_text(
            f"✅ Рецепт сохранён как «{new_slug}»",
            reply_markup=_recipe_kb(recipe.category, new_rk),
        )
        logger.info(f"Recipe saved as new via button: {recipe.category}/{new_slug}")

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
    """Перемещение рецепта в другую категорию (единая категория для всех групп)"""
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
        # Читаем текущий рецепт из GitHub
        content = await gramax.get_recipe_content(old_category, f"{slug}.md")

        # Обновляем category в YAML frontmatter markdown-файла
        content = content.replace(
            f"category: {old_category}",
            f"category: {new_category}",
        )

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

        # Обновляем категорию во ВСЕХ группах
        gm.move_recipe_category(old_category, slug, new_category)

        # Обновляем source_index
        source_url = gm.find_source_by_slug(old_category, slug)
        if source_url:
            gm.register_source(source_url, new_category, slug)

        # Обновляем кэш
        cache.update(rk, {"category": new_category, "slug": slug, "group_id": cached.get("group_id")})

        await callback.message.edit_text(
            f"✅ Рецепт «{slug}» перемещён в «{new_category}»",
            reply_markup=_recipe_kb(new_category, rk),
        )
        logger.info(f"Recipe moved: {old_category}/{slug} -> {new_category}/{slug}")

    except Exception as e:
        logger.error(f"Move error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Не удалось переместить рецепт. Попробуйте позже")

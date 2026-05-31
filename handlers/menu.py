"""Persistent menu + случайный рецепт по категории"""

import logging
import random

from aiogram import Router, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

import config
import services.gramax as gramax
import services.group_manager as gm
import services.cache as cache
import services.rotation as rotation

logger = logging.getLogger(__name__)

router = Router()

VALID_CATEGORIES = ["завтрак", "основное блюдо", "десерт"]


class SearchState(StatesGroup):
    waiting_for_ingredient = State()

# Кнопки меню всегда видны внизу чата
MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌅 Завтрак")],
        [KeyboardButton(text="🍽 Основное блюдо")],
        [KeyboardButton(text="🍰 Десерт")],
        [KeyboardButton(text="🔍 Поиск")],
        [KeyboardButton(text="👥 Мои группы")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


def _parse_category(text: str) -> str | None:
    """Определяет категорию из текста кнопки"""
    mapping = {
        "🌅 Завтрак": "завтрак",
        "🍽 Основное блюдо": "основное блюдо",
        "🍰 Десерт": "десерт",
    }
    return mapping.get(text)


def _format_recipe_from_markdown(md_content: str) -> str:
    """Форматирует Markdown контент для отправки в чат"""
    lines = md_content.strip().split("\n")

    # Пропускаем YAML frontmatter
    in_frontmatter = False
    content_lines = []
    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        content_lines.append(line)

    # Убираем пустые строки в начале
    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)

    text = "\n".join(content_lines)

    # Убираем Markdown заголовки, заменяем на читаемый формат
    text = text.replace("## Ингредиенты", "📋 Ингредиенты:")
    text = text.replace("## Способ приготовления", "👨‍🍳 Приготовление:")
    text = text.replace("# ", "🍳 ")

    return text


async def _try_get_random_recipe(
    group_id: str, category: str, *, exclude: list[str] | None = None
) -> tuple[str, str] | None:
    """
    Пытается получить случайный рецепт из категории.
    Если файл в GitHub не найден (404) — пропускает «мёртвую» запись и пробует другой.
    Возвращает (slug, content) или None.
    """
    group_slugs = gm.get_group_recipes_by_category(group_id, category)

    if not group_slugs:
        return None

    # Фильтруем исключённые из rotation рецепты
    if exclude:
        exclude_set = set(exclude)
        filtered = [s for s in group_slugs if s not in exclude_set]
        if filtered:
            group_slugs = filtered
        # Если после фильтрации ничего не осталось — используем полный список
        # (все рецепты показаны, начинаем новый цикл)

    # Перемешиваем, чтобы не зациклиться на одном мёртвом рецепте
    random.shuffle(group_slugs)

    for slug in group_slugs:
        filename = f"{slug}.md"
        try:
            content = await gramax.get_recipe_content(category, filename)
            return slug, content
        except gramax.RecipeNotFoundError:
            # Рецепт удалён из GitHub — пропускаем без удаления
            logger.warning(f"Stale recipe {category}/{slug} not found in GitHub, skipping")
            continue
        except Exception:
            # Другая ошибка — пробрасываем
            raise

    return None


async def _try_get_recipe_from_slugs(
    slugs: list[str], category: str, group_id: str, *, exclude: list[str] | None = None
) -> tuple[str, str] | None:
    """
    Пытается получить рецепт из списка slugs.
    Если файл в GitHub не найден (404) — пропускает и пробует следующий.
    Возвращает (slug, content) или None.
    """
    if not slugs:
        return None

    # Фильтруем исключённые из rotation рецепты
    if exclude:
        exclude_set = set(exclude)
        filtered = [s for s in slugs if s not in exclude_set]
        if filtered:
            slugs = filtered
        # Если после фильтрации ничего не осталось — используем полный список

    # Перемешиваем для случайного выбора
    random.shuffle(slugs)

    for slug in slugs:
        try:
            content = await gramax.get_recipe_content(category, f"{slug}.md")
            return slug, content
        except gramax.RecipeNotFoundError:
            # Рецепт удалён из GitHub — пропускаем
            logger.warning(f"Stale recipe {category}/{slug} not found in GitHub, skipping")
            continue
        except Exception:
            # Другая ошибка — пробрасываем
            raise

    return None


@router.message(F.text.in_(["🌅 Завтрак", "🍽 Основное блюдо", "🍰 Десерт"]))
async def handle_menu_category(message: Message) -> None:
    """Обработка нажатия кнопки меню — случайный рецепт из категории"""
    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)
    category = _parse_category(message.text)
    if not category:
        return

    # Получаем список исключённых из rotation
    excluded = rotation.get_excluded(user_id, category)

    result = await _try_get_random_recipe(group_id, category, exclude=excluded)

    if not result:
        group = gm.get_group(group_id)
        group_name = group.name if group else "Неизвестная"
        await message.answer(
            f"📭 Пока нет рецептов в категории «{category}» в группе «{group_name}».\n"
            f"Отправьте мне ссылку на рилс с рецептом!"
        )
        return

    slug, content = result

    # Добавляем показанный рецепт в rotation
    total_count = len(gm.get_group_recipes_by_category(group_id, category))
    rotation.add(user_id, category, slug, total_count)

    formatted = _format_recipe_from_markdown(content)

    # Добавляем inline-кнопки
    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})

    cc = config.CATEGORY_TO_CODE.get(category, "o")
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(
        text="🎲 Другой рецепт", callback_data=f"rnd:{cc}"
    )
    builder.button(
        text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}"
    )
    # Ищем source URL для кнопки "Открыть Reels"
    source_url = gm.find_source_by_slug(category, slug)
    if source_url:
        builder.button(text="▶️ Открыть Reels", url=source_url)
        builder.adjust(2, 2)
    else:
        builder.adjust(2, 1)

    await message.answer(
        f"🎲 Случайный рецепт:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("rnd:"))
async def handle_random_callback(callback: CallbackQuery) -> None:
    """Обработка кнопки 'Другой рецепт'"""
    user_id = callback.from_user.id
    group_id = gm.get_user_active_group(user_id)

    parts = callback.data.split(":")
    if len(parts) != 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, cc = parts
    category = config.CODE_TO_CATEGORY.get(cc, "основное блюдо")

    await callback.answer("Выбираю другой рецепт...")

    # Получаем список исключённых из rotation
    excluded = rotation.get_excluded(user_id, category)

    result = await _try_get_random_recipe(group_id, category, exclude=excluded)

    if not result:
        await callback.message.edit_text(
            f"📭 Пока нет рецептов в категории «{category}»"
        )
        return

    slug, content = result

    # Добавляем показанный рецепт в rotation
    total_count = len(gm.get_group_recipes_by_category(group_id, category))
    rotation.add(user_id, category, slug, total_count)

    formatted = _format_recipe_from_markdown(content)

    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(
        text="🎲 Другой рецепт", callback_data=f"rnd:{cc}"
    )
    builder.button(
        text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}"
    )
    # Ищем source URL для кнопки "Открыть Reels"
    source_url = gm.find_source_by_slug(category, slug)
    if source_url:
        builder.button(text="▶️ Открыть рилс", url=source_url)
        builder.adjust(2, 2)
    else:
        builder.adjust(2, 1)

    await callback.message.edit_text(
        f"🎲 Случайный рецепт:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )


# ── Поиск по ингредиенту ────────────────────────────────────────────────

@router.message(F.text == "🔍 Поиск")
async def handle_search_start(message: Message) -> None:
    """Начало поиска по ингредиенту"""
    await message.answer("🔎 Введите ингредиент для поиска:")
    await message.set_state(SearchState.waiting_for_ingredient)


@router.message(SearchState.waiting_for_ingredient)
async def handle_search_ingredient(message: Message) -> None:
    """Обработка ввод ингредиента"""
    ingredient = message.text.strip()
    if not ingredient:
        await message.answer("Пожалуйста, введите ингредиент:")
        return

    user_id = message.from_user.id
    group_id = gm.get_user_active_group(user_id)
    
    # Сбрасываем FSM
    await message.clear_state()
    
    # Кэшируем данные
    cache_key = cache.put({"ingredient": ingredient, "group_id": group_id})
    
    # Показываем inline-клавиатуру с категориями
    builder = InlineKeyboardBuilder()
    for cat in VALID_CATEGORIES:
        cc = config.CATEGORY_TO_CODE.get(cat, "o")
        builder.button(text=cat.capitalize(), callback_data=f"srch:{cc}:{cache_key}")
    builder.adjust(1)
    
    await message.answer(
        f"🔎 Выберите категорию для поиска «{ingredient}»:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("srch:"))
async def handle_search_category(callback: CallbackQuery) -> None:
    """Выполнение поиска по выбранной категории"""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    
    _, cc, cache_key = parts
    cached = cache.get(cache_key)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Попробуйте снова")
        return
    
    ingredient = cached["ingredient"]
    group_id = cached["group_id"]
    category = config.CODE_TO_CATEGORY.get(cc, "основное блюдо")
    user_id = callback.from_user.id
    
    await callback.answer(f"Ищу {ingredient}...")
    
    # Выполняем поиск
    slugs = gm.search_recipes_by_ingredient(group_id, ingredient, category)
    
    if not slugs:
        await callback.message.edit_text(
            f"📭 Рецептов с ингредиентом «{ingredient}» в категории «{category}» не найдено"
        )
        return

    # Получаем список исключённых из rotation
    excluded = rotation.get_excluded(user_id, category)
    
    # Пытаемся получить рецепт (с пропуском удалённых)
    result = await _try_get_recipe_from_slugs(slugs, category, group_id, exclude=excluded)
    
    if not result:
        await callback.message.edit_text(
            f"📭 Не удалось загрузить рецепты с ингредиентом «{ingredient}» в категории «{category}»"
        )
        return
    
    slug, content = result

    # Добавляем показанный рецепт в rotation
    rotation.add(user_id, category, slug, len(slugs))

    formatted = _format_recipe_from_markdown(content)
    
    # Кэшируем данные для кнопок
    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(text="🎲 Другой рецепт", callback_data=f"srnd:{cc}:{cache_key}")
    builder.button(text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}")
    builder.adjust(2, 1)
    
    await callback.message.edit_text(
        f"🔎 Результат поиска «{ingredient}»:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("srnd:"))
async def handle_search_random(callback: CallbackQuery) -> None:
    """Другой результат поиска"""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    
    _, cc, cache_key = parts
    cached = cache.get(cache_key)
    if not cached:
        await callback.message.edit_text("❌ Данные устарели. Попробуйте снова")
        return
    
    ingredient = cached["ingredient"]
    group_id = cached["group_id"]
    category = config.CODE_TO_CATEGORY.get(cc, "основное блюдо")
    user_id = callback.from_user.id
    
    await callback.answer("Выбираю другой рецепт...")
    
    # Выполняем поиск
    slugs = gm.search_recipes_by_ingredient(group_id, ingredient, category)
    
    if not slugs:
        await callback.message.edit_text(
            f"📭 Рецептов с ингредиентом «{ingredient}» в категории «{category}» не найдено"
        )
        return

    # Получаем список исключённых из rotation
    excluded = rotation.get_excluded(user_id, category)
    
    # Пытаемся получить рецепт (с пропуском удалённых)
    result = await _try_get_recipe_from_slugs(slugs, category, group_id, exclude=excluded)
    
    if not result:
        await callback.message.edit_text(
            f"📭 Не удалось загрузить рецепты с ингредиентом «{ingredient}» в категории «{category}»"
        )
        return
    
    slug, content = result

    # Добавляем показанный рецепт в rotation
    rotation.add(user_id, category, slug, len(slugs))

    formatted = _format_recipe_from_markdown(content)
    
    # Кэшируем данные для кнопок
    rk = cache.put({"category": category, "slug": slug, "group_id": group_id})
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"del:{cc}:{rk}")
    builder.button(text="🎲 Другой рецепт", callback_data=f"srnd:{cc}:{cache_key}")
    builder.button(text="📂 Другая категория", callback_data=f"rcat:{cc}:{rk}")
    builder.adjust(2, 1)
    
    await callback.message.edit_text(
        f"🔎 Результат поиска «{ingredient}»:\n\n{formatted}",
        reply_markup=builder.as_markup(),
    )
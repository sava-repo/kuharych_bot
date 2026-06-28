"""Генерация рецепта через GLM-5 API"""

import logging
from pathlib import Path

import httpx

import config
from exceptions import NotARecipeError, RecipeParseError
from models.recipe import Recipe

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.txt"

DEFAULT_CATEGORIES_FALLBACK: list[str] = ["завтрак", "основное блюдо", "десерт"]
DEFAULT_CATEGORY_FALLBACK: str = "основное блюдо"


def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _build_system_prompt(categories: list[str], default: str) -> str:
    """Подставляет список категорий активной группы в шаблон промпта."""
    template = _load_system_prompt()
    if not categories:
        categories = DEFAULT_CATEGORIES_FALLBACK
        default = default or DEFAULT_CATEGORY_FALLBACK
    categories_str = " / ".join(categories)
    return template.replace("{categories}", categories_str).replace("{default}", default)


def _build_user_prompt(transcription: str | None, caption: str | None) -> str:
    caption_text = caption if caption else "(нет описания)"
    if transcription is None:
        # Fallback: речь не распознана — извлекаем рецепт только из описания
        return (
            f"(Транскрибация видео недоступна — речь не распознана)\n\n"
            f"Рецепт из описания под видео:\n{caption_text}"
        )
    return (
        f"Транскрибация видео:\n{transcription}\n\n"
        f"Описание под видео:\n{caption_text}"
    )


def _parse_recipe_response(
    response_text: str,
    source: str,
    categories: list[str],
    default: str,
) -> Recipe:
    """
    Парсит ответ GLM-5 в структурированный Recipe.
    Категория выбирается из переданного списка categories; при отсутствии
    уверенного совпадения используется default.
    """
    text = response_text.strip()

    # Проверяем "не рецепт"
    if "НЕ РЕЦЕПТ" in text.upper():
        raise NotARecipeError("Видео не содержит рецепт")

    # Извлекаем название
    title = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.lower().startswith("название:"):
            title = line.split(":", 1)[1].strip()
            break

    if not title:
        # Попробуем найти первую строку как название
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith(("-", "Шаг", "Категория", "Ингредиенты", "Способ")):
                title = line
                break

    # Извлекаем категорию — матчинг против списка категорий группы
    category = default or DEFAULT_CATEGORY_FALLBACK
    cat_lower_map = {c.lower(): c for c in categories}
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("категория:"):
            cat_text = stripped.split(":", 1)[1].strip().lower()
            for cat_low, cat_orig in cat_lower_map.items():
                if cat_low in cat_text or cat_text in cat_low:
                    category = cat_orig
                    break
            break

    # Извлекаем ингредиенты
    ingredients: list[str] = []
    in_ingredients = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("ингредиенты"):
            in_ingredients = True
            continue
        if stripped.lower().startswith("способ приготовления"):
            in_ingredients = False
            continue
        if stripped.lower().startswith("категория"):
            in_ingredients = False
            continue
        if in_ingredients and stripped.startswith("-"):
            ingredients.append(stripped.lstrip("- ").strip())

    # Извлекаем шаги
    steps: list[str] = []
    in_steps = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("способ приготовления"):
            in_steps = True
            continue
        if stripped.lower().startswith("категория"):
            in_steps = False
            continue
        if in_steps and stripped.lower().startswith("шаг"):
            # "Шаг 1: Нарезать лук" -> "Нарезать лук"
            step_text = stripped.split(":", 1)
            if len(step_text) > 1:
                steps.append(step_text[1].strip())
            else:
                # "Шаг 1: Нарезать лук" might have different format
                parts = stripped.split(None, 1)
                if len(parts) > 1:
                    step_content = parts[1]
                    # Убираем номер шага если есть
                    if ":" in step_content:
                        step_content = step_content.split(":", 1)[1].strip()
                    steps.append(step_content)
        elif in_steps and stripped and not stripped.startswith(("Название", "Ингредиенты", "Категория")):
            # Возможно шаги без явного "Шаг N"
            if stripped[0].isdigit() and "." in stripped:
                step_text = stripped.split(".", 1)[1].strip()
                if step_text:
                    steps.append(step_text)

    if not title:
        raise RecipeParseError("Не удалось извлечь название блюда из ответа")

    if not ingredients:
        raise RecipeParseError("Не удалось извлечь ингредиенты из ответа")

    if not steps:
        raise RecipeParseError("Не удалось извлечь шаги приготовления из ответа")

    # Генерируем теги из названия и ингредиентов
    tags = _generate_tags(title, ingredients)

    # Извлекаем КБЖУ (тотальные на всё блюдо) и порции
    nutrition = _extract_nutrition(text)

    return Recipe(
        title=title,
        ingredients=ingredients,
        steps=steps,
        category=category,
        source=source,
        tags=tags,
        portions=nutrition["portions"],
        calories=nutrition["calories"],
        protein=nutrition["protein"],
        fat=nutrition["fat"],
        carbs=nutrition["carbs"],
    )


def _extract_nutrition(text: str) -> dict[str, int]:
    """Извлекает КБЖУ и порции из ответа LLM.

    Ищет строки вида «Порции: 4», «Калории: 1280» и т.п. Берёт первое целое
    число в значении (терпимо к единицам вроде «1280 ккал»). При отсутствии
    строки или не-числе поле остаётся 0.
    """
    mapping = {
        "порции": "portions",
        "калории": "calories",
        "белки": "protein",
        "жиры": "fat",
        "углеводы": "carbs",
    }
    result = {field: 0 for field in mapping.values()}
    for line in text.split("\n"):
        stripped = line.strip()
        low = stripped.lower()
        for ru_key, field in mapping.items():
            if low.startswith(f"{ru_key}:"):
                result[field] = _parse_nutrition_int(stripped.split(":", 1)[1])
                break
    return result


def _parse_nutrition_int(value: str) -> int:
    """Первое целое число в строке значения; 0 при отсутствии."""
    for token in value.split():
        token = token.strip(".,;:()")
        if token.isdigit():
            return int(token)
    return 0


def _generate_tags(title: str, ingredients: list[str]) -> list[str]:
    """Генерирует теги из названия и ингредиентов"""
    tags = set()

    # Из названия берём ключевые слова
    for word in title.lower().split():
        word = word.strip(".,!?;:")
        if len(word) > 2:
            tags.add(word)

    # Из ингредиентов берём название без количества
    for ing in ingredients:
        # Берём первое слово ингредиента (продукт)
        parts = ing.lower().split()
        if parts:
            product = parts[0].strip(".,!?;:")
            if len(product) > 2:
                tags.add(product)

    return list(tags)[:10]


async def generate_recipe(
    transcription: str | None,
    caption: str | None,
    source: str,
    categories: list[str] | None = None,
    default: str = "",
) -> Recipe:
    """
    Отправляет транскрибацию в GLM-5 и возвращает структурированный рецепт.

    categories / default определяют динамический список категорий активной
    группы, который подставляется в системный промпт.
    """
    cats = categories or DEFAULT_CATEGORIES_FALLBACK
    default = default or DEFAULT_CATEGORY_FALLBACK
    system_prompt = _build_system_prompt(cats, default)
    user_prompt = _build_user_prompt(transcription, caption)

    t_len = f"{len(transcription)} chars" if transcription else "None (caption fallback)"
    logger.info(f"Sending to GLM-5: transcription={t_len}, caption={bool(caption)}, categories={len(cats)}")

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.post(
            config.GLM_API_URL,
            headers={
                "Authorization": f"Bearer {config.GLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.GLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            },
        )

    if response.status_code != 200:
        logger.error(f"GLM-5 API error: {response.status_code} {response.text}")
        raise RuntimeError(f"GLM-5 API error: {response.status_code}")

    result = response.json()
    content = result["choices"][0]["message"]["content"].strip()

    logger.info(f"GLM-5 response ({len(content)} chars): {content[:200]}...")

    return _parse_recipe_response(content, source, cats, default)
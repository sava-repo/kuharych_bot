"""Генерация рецепта через GLM-5 API"""

import logging
from pathlib import Path

import httpx

import config
from models.recipe import Recipe

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.txt"

VALID_CATEGORIES = ["завтрак", "основное блюдо", "десерт"]


def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


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


def _parse_recipe_response(response_text: str, source: str) -> Recipe:
    """
    Парсит ответ GLM-5 в структурированный Recipe.
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

    # Извлекаем категорию
    category = "основное блюдо"  # по умолчанию
    for line in text.split("\n"):
        line = line.strip().lower()
        if line.startswith("категория:"):
            cat_text = line.split(":", 1)[1].strip()
            for valid_cat in VALID_CATEGORIES:
                if valid_cat in cat_text:
                    category = valid_cat
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

    return Recipe(
        title=title,
        ingredients=ingredients,
        steps=steps,
        category=category,
        source=source,
        tags=tags,
    )


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


class NotARecipeError(Exception):
    """Видео не содержит рецепт"""
    pass


class RecipeParseError(Exception):
    """Ошибка парсинга ответа GLM-5"""
    pass


async def generate_recipe(transcription: str | None, caption: str | None, source: str) -> Recipe:
    """
    Отправляет транскрибацию в GLM-5 и возвращает структурированный рецепт.
    """
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(transcription, caption)

    t_len = f"{len(transcription)} chars" if transcription else "None (caption fallback)"
    logger.info(f"Sending to GLM-5: transcription={t_len}, caption={bool(caption)}")

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

    return _parse_recipe_response(content, source)
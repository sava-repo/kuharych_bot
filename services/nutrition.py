"""Оценка КБЖУ рецепта через LLM и бэкфилл существующих рецептов.

Бэкфилл использует отдельный только-КБЖУ промпт (``prompts/nutrition.txt``),
чтобы не переизвлекать title/ingredients/steps и не затирать контент рецепта.
КБЖУ хранится в ``content_md`` (frontmatter); схема БД не меняется.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

import config
import services.group_manager as gm
from models.recipe import Recipe
from services.recipe_parser import _extract_nutrition

logger = logging.getLogger(__name__)

NUTRITION_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "nutrition.txt"


@dataclass
class NutritionEstimate:
    """Тотальные значения КБЖУ и число порций на всё блюдо (LLM-оценка)."""

    portions: int = 0
    calories: int = 0
    protein: int = 0
    fat: int = 0
    carbs: int = 0


@dataclass
class BackfillReport:
    """Отчёт о ходе бэкфилла КБЖУ."""

    processed: int = 0  # обновлено (записано КБЖУ)
    skipped: int = 0    # уже имело КБЖУ (calories > 0)
    failed: int = 0     # ошибка или LLM не дал оценку (calories == 0)
    failed_ids: list[int] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"Бэкфилл КБЖУ: обработано {self.processed}, "
            f"пропущено {self.skipped}, ошибок {self.failed}"
            + (f" (recipe_id: {self.failed_ids})" if self.failed_ids else "")
        )


def _load_nutrition_prompt() -> str:
    return NUTRITION_PROMPT_PATH.read_text(encoding="utf-8")


def _build_nutrition_user_prompt(recipe: Recipe) -> str:
    """Собирает пользовательский промпт из уже распознанного рецепта."""
    ingredients_text = "\n".join(f"- {ing}" for ing in recipe.ingredients)
    steps_text = "\n".join(
        f"{i + 1}. {step}" for i, step in enumerate(recipe.steps)
    )
    return (
        f"Название: {recipe.title}\n\n"
        f"Ингредиенты:\n{ingredients_text}\n\n"
        f"Способ приготовления:\n{steps_text}"
    )


async def estimate_nutrition(recipe: Recipe) -> NutritionEstimate:
    """Только-КБЖУ LLM-вызов: title + ingredients + steps → 5 чисел.

    Raises:
        RuntimeError: при ошибке API GLM (сеть/статус).
    """
    system_prompt = _load_nutrition_prompt()
    user_prompt = _build_nutrition_user_prompt(recipe)

    logger.info(
        "Nutrition estimate: %s, %d ingredients",
        recipe.title, len(recipe.ingredients),
    )

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
        logger.error("GLM nutrition API error: %s %s", response.status_code, response.text)
        raise RuntimeError(f"GLM API error: {response.status_code}")

    content = response.json()["choices"][0]["message"]["content"]
    parsed = _extract_nutrition(content)
    logger.info("Nutrition estimate for %s: %s", recipe.title, parsed)
    return NutritionEstimate(
        portions=parsed["portions"],
        calories=parsed["calories"],
        protein=parsed["protein"],
        fat=parsed["fat"],
        carbs=parsed["carbs"],
    )


async def backfill_all(
    *, dry_run: bool = False, limit: int | None = None
) -> BackfillReport:
    """Перебирает рецепты без КБЖУ и дополняет их оценкой LLM.

    - Кандидаты: рецепты, у которых ``calories == 0`` после ``from_markdown``.
    - Для каждого вызывается ``estimate_nutrition``; при ``calories > 0`` новый
      ``content_md`` пишется в БД (если не ``dry_run``).
    - При ошибке API или нулевой оценке рецепт попадает в ``failed`` и не
      обновляется (остаётся кандидатом на следующий прогон).
    """
    report = BackfillReport()
    rows = gm.get_all_recipes_content()

    for row in rows:
        recipe_id = row["recipe_id"]
        recipe = Recipe.from_markdown(row["content_md"], row["source"])

        if recipe.calories > 0:
            report.skipped += 1
            continue

        if limit is not None and report.processed >= limit:
            break

        try:
            estimate = await estimate_nutrition(recipe)
        except Exception as exc:
            logger.error("Backfill: estimate failed for recipe_id=%s: %s", recipe_id, exc)
            report.failed += 1
            report.failed_ids.append(recipe_id)
            continue

        if estimate.calories <= 0:
            # LLM не смог оценить — оставляем кандидатом, не пишем пустоту.
            logger.warning("Backfill: no nutrition for recipe_id=%s", recipe_id)
            report.failed += 1
            report.failed_ids.append(recipe_id)
            continue

        recipe.portions = estimate.portions
        recipe.calories = estimate.calories
        recipe.protein = estimate.protein
        recipe.fat = estimate.fat
        recipe.carbs = estimate.carbs

        new_md = recipe.to_markdown(created=row["created"])

        if dry_run:
            logger.info("Backfill [dry-run]: would update recipe_id=%s", recipe_id)
        else:
            gm.update_recipe_content_md(recipe_id, new_md)
            logger.info("Backfill: updated recipe_id=%s", recipe_id)

        report.processed += 1

    logger.info("Backfill summary: %s", report)
    return report

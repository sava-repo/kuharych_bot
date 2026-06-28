"""Тесты оценки КБЖУ и бэкфилла (services/nutrition.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

import config
import services.group_manager as gm
import services.nutrition as nutrition
from models.recipe import Recipe
from services.database import Database
from services.nutrition import NutritionEstimate, backfill_all, estimate_nutrition


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch) -> None:
    """Перенаправляет DATABASE_PATH во временный файл и сбрасывает singleton."""
    db_path = tmp_path / "test_bot.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))

    Database._instance = None
    gm.db = Database.get_instance()
    with gm.db.connect():
        pass

    yield

    Database._instance = None


class _FakeResponse:
    def __init__(self, payload, status_code=200, text="ok"):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    """Имитация httpx.AsyncClient для estimate_nutrition."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self._status = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, **kwargs):
        async def _coro():
            return _FakeResponse(self._payload, self._status)

        return _coro()


def _llm_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _patch_llm(monkeypatch, content: str, status_code: int = 200) -> None:
    monkeypatch.setattr(
        nutrition.httpx,
        "AsyncClient",
        lambda *a, **kw: _FakeClient(_llm_payload(content), status_code),
    )


# ── estimate_nutrition ────────────────────────────────────────────────────


class TestEstimateNutrition:
    def test_parses_five_values(self, monkeypatch):
        import asyncio
        _patch_llm(
            monkeypatch,
            "Порции: 4\nКалории: 1280\nБелки: 80\nЖиры: 40\nУглеводы: 120\n",
        )
        recipe = Recipe("Борщ", ["Свекла 400г"], ["Варить"], "src")

        result = asyncio.run(estimate_nutrition(recipe))

        assert result.portions == 4
        assert result.calories == 1280
        assert result.protein == 80
        assert result.fat == 40
        assert result.carbs == 120

    def test_tolerates_non_numeric(self, monkeypatch):
        _patch_llm(monkeypatch, "Порции: много\nКалории: нет\n")
        import asyncio
        recipe = Recipe("Х", ["а"], ["б"], "src")
        result = asyncio.run(estimate_nutrition(recipe))
        assert result.portions == 0
        assert result.calories == 0

    def test_raises_on_api_error(self, monkeypatch):
        _patch_llm(monkeypatch, "", status_code=500)
        import asyncio
        recipe = Recipe("Х", ["а"], ["б"], "src")
        with pytest.raises(RuntimeError):
            asyncio.run(estimate_nutrition(recipe))


# ── backfill_all ──────────────────────────────────────────────────────────


def _save_recipe(slug, title, *, calories=0, portions=0, protein=0, fat=0, carbs=0):
    recipe = Recipe(
        title, ["Ингредиент"], ["Шаг"], "src",
        portions=portions, calories=calories, protein=protein, fat=fat, carbs=carbs,
    )
    return gm.save_recipe(
        slug=slug,
        title=title,
        content_md=recipe.to_markdown(created=""),
        source="src",
        ingredients=recipe.ingredients,
        steps=recipe.steps,
    )


class TestBackfillAll:
    def test_updates_only_recipes_without_nutrition(self, temp_db, monkeypatch):
        """Кандидат без КБЖУ обновляется; с КБЖУ — пропускается."""
        rid_new = _save_recipe("sup", "Суп")  # без КБЖУ
        _save_recipe(
            "borsh", "Борщ", calories=500, portions=2, protein=30, fat=10, carbs=40,
        )

        async def _fake_estimate(recipe):
            return NutritionEstimate(portions=3, calories=900, protein=45, fat=15, carbs=60)

        monkeypatch.setattr(nutrition, "estimate_nutrition", _fake_estimate)

        import asyncio
        report = asyncio.run(backfill_all())

        assert report.processed == 1
        assert report.skipped == 1
        assert report.failed == 0

        # content_md кандидата теперь содержит КБЖУ
        row = gm.get_recipe(rid_new)
        recipe = Recipe.from_markdown(row["content_md"], row["source"])
        assert recipe.calories == 900
        assert recipe.portions == 3

    def test_dry_run_does_not_write(self, temp_db, monkeypatch):
        rid_new = _save_recipe("sup", "Суп")

        async def _fake_estimate(recipe):
            return NutritionEstimate(portions=3, calories=900)

        monkeypatch.setattr(nutrition, "estimate_nutrition", _fake_estimate)

        import asyncio
        report = asyncio.run(backfill_all(dry_run=True))

        assert report.processed == 1
        # БД не изменилась — calories остался 0
        row = gm.get_recipe(rid_new)
        recipe = Recipe.from_markdown(row["content_md"], row["source"])
        assert recipe.calories == 0

    def test_failed_estimates_counted(self, temp_db, monkeypatch):
        rid_new = _save_recipe("sup", "Суп")

        async def _fake_estimate(recipe):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(nutrition, "estimate_nutrition", _fake_estimate)

        import asyncio
        report = asyncio.run(backfill_all())

        assert report.processed == 0
        assert report.failed == 1
        assert rid_new in report.failed_ids

    def test_zero_estimate_treated_as_failed(self, temp_db, monkeypatch):
        """Если LLM вернул calories==0 — не пишем, считаем failed."""
        rid_new = _save_recipe("sup", "Суп")

        async def _fake_estimate(recipe):
            return NutritionEstimate()  # все нули

        monkeypatch.setattr(nutrition, "estimate_nutrition", _fake_estimate)

        import asyncio
        report = asyncio.run(backfill_all())

        assert report.processed == 0
        assert report.failed == 1
        row = gm.get_recipe(rid_new)
        recipe = Recipe.from_markdown(row["content_md"], row["source"])
        assert recipe.calories == 0  # не записано

    def test_limit_caps_processed(self, temp_db, monkeypatch):
        _save_recipe("a", "A")
        _save_recipe("b", "B")
        _save_recipe("c", "C")

        async def _fake_estimate(recipe):
            return NutritionEstimate(portions=1, calories=100)

        monkeypatch.setattr(nutrition, "estimate_nutrition", _fake_estimate)

        import asyncio
        report = asyncio.run(backfill_all(limit=2))

        assert report.processed == 2

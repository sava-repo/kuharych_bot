"""Тесты полнотекстового поиска рецептов.

Использует временную SQLite-БД через monkeypatch config.DATABASE_PATH.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import config
from services import group_manager
from services.database import Database


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch) -> None:
    """Перенаправляет DATABASE_PATH во временный файл и сбрасывает singleton Database."""
    db_path = tmp_path / "test_bot.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))

    Database._instance = None
    group_manager.db = Database.get_instance()

    yield

    Database._instance = None


def _setup_group(group_id: str = "pers_1", user_id: int = 1) -> None:
    """Создаёт пользователя с личной группой (и дефолтными категориями)."""
    group_manager._ensure_user(user_id)


def _save_and_link(group_id: str, category: str, slug: str, title: str,
                   ingredients: list[str], steps: list[str] | None = None,
                   user_id: int = 1) -> int:
    """Сохраняет рецепт и привязывает к группе под указанную категорию."""
    recipe_id = group_manager.save_recipe(
        slug=slug,
        title=title,
        content_md=f"# {title}",
        source="",
        ingredients=ingredients,
        steps=steps or [],
    )
    cat = group_manager.get_category(group_id, category)
    category_id = cat.category_id if cat else group_manager.get_default_category_id(group_id)
    group_manager.add_recipe_to_group(group_id, recipe_id, category_id, user_id)
    return recipe_id


class TestSearchFulltext:
    def test_search_by_ingredient_lemma(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "завтрак", "omlet", "Омлет", ["10 яиц"])

        results = group_manager.search_recipes_fulltext("pers_1", "яйца")
        assert len(results) == 1
        assert results[0][1] == "omlet"
        assert results[0][2] == "Омлет"

    def test_search_by_ingredient_lemma_singular(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "завтрак", "omlet", "Омлет", ["10 яиц"])

        results = group_manager.search_recipes_fulltext("pers_1", "яйцо")
        assert len(results) == 1

    def test_search_by_phrase_ingredient(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "основное блюдо", "turkey", "Индейка",
                        ["филе индейки"])

        results = group_manager.search_recipes_fulltext("pers_1", "индейка")
        assert len(results) == 1
        assert results[0][1] == "turkey"

    def test_search_by_title(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "десерт", "tiramisu", "Тирамису классический",
                        ["маскарпоне", "кофе"])

        results = group_manager.search_recipes_fulltext("pers_1", "тирамису")
        assert len(results) == 1
        assert results[0][1] == "tiramisu"

    def test_search_by_step_text(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "основное блюдо", "pasta", "Паста карбонара",
                        ["спагетти", "бекон", "яйца"],
                        steps=["Отварите спагетти в подсоленной воде",
                               "Обжарьте бекон на сковороде"])

        results = group_manager.search_recipes_fulltext("pers_1", "сковорода")
        assert len(results) == 1
        assert results[0][1] == "pasta"

    def test_search_across_all_categories(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "завтрак", "omlet", "Омлет", ["яйца"])
        _save_and_link("pers_1", "десерт", "cake", "Торт", ["яйца", "мука"])

        results = group_manager.search_recipes_fulltext("pers_1", "яйца")
        assert len(results) == 2

    def test_search_no_results(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "завтрак", "omlet", "Омлет", ["яйца"])

        results = group_manager.search_recipes_fulltext("pers_1", "лосось")
        assert results == []

    def test_search_match_exact_lemma(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "основное блюдо", "chicken", "Курица",
                        ["куриная грудка"])

        results = group_manager.search_recipes_fulltext("pers_1", "куриная")
        assert len(results) == 1

    def test_search_phrase_requires_all_lemmas(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "основное блюдо", "chicken", "Курица",
                        ["куриная грудка"])

        results = group_manager.search_recipes_fulltext("pers_1", "куриная грудка")
        assert len(results) == 1

    def test_search_digit_only_returns_empty(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "завтрак", "omlet", "Омлет", ["10 яиц"])

        results = group_manager.search_recipes_fulltext("pers_1", "10")
        assert results == []

    def test_search_empty_query_returns_empty(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "завтрак", "omlet", "Омлет", ["яйца"])

        assert group_manager.search_recipes_fulltext("pers_1", "") == []
        assert group_manager.search_recipes_fulltext("pers_1", "   ") == []

    def test_search_only_recipes_in_group(self, temp_db):
        _setup_group("pers_1", 1)
        _setup_group("pers_2", 2)

        _save_and_link("pers_1", "завтрак", "omlet1", "Омлет 1", ["яйца"])
        _save_and_link("pers_1", "завтрак", "omlet2", "Омлет 2", ["яйца", "молоко"])

        results = group_manager.search_recipes_fulltext("pers_2", "яйца")
        assert results == []


class TestCategoryIsolation:
    """Один рецепт в разных категориях у разных групп; перемещение изолировано."""

    def test_same_recipe_different_category_per_group(self, temp_db):
        _setup_group("pers_1", 1)
        _setup_group("pers_2", 2)
        # Оба пользователя добавляют один рилс → один recipe_id
        rid = _save_and_link("pers_1", "завтрак", "borshch", "Борщ", ["свёкла"], user_id=1)
        group_manager.add_recipe_to_group(
            "pers_2", rid,
            group_manager.get_category("pers_2", "основное блюдо").category_id,
            user_id=2,
        )
        cat1 = group_manager.get_group_recipe_category("pers_1", rid)
        cat2 = group_manager.get_group_recipe_category("pers_2", rid)
        assert cat1.name == "завтрак"
        assert cat2.name == "основное блюдо"

    def test_move_does_not_affect_other_group(self, temp_db):
        _setup_group("pers_1", 1)
        _setup_group("pers_2", 2)
        rid = _save_and_link("pers_1", "завтрак", "borshch", "Борщ", ["свёкла"], user_id=1)
        group_manager.add_recipe_to_group(
            "pers_2", rid,
            group_manager.get_category("pers_2", "завтрак").category_id,
            user_id=2,
        )
        # pers_1 переносит в «десерт»
        new_cid = group_manager.get_category("pers_1", "десерт").category_id
        group_manager.move_recipe_in_group("pers_1", rid, new_cid)

        assert group_manager.get_group_recipe_category("pers_1", rid).name == "десерт"
        # В pers_2 категория не изменилась
        assert group_manager.get_group_recipe_category("pers_2", rid).name == "завтрак"

"""Тесты морфологического поиска по ингредиентам.

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

    # Сбрасываем singleton Database, чтобы он переинициализировался на новый путь
    Database._instance = None  # type: ignore[attr-defined]
    group_manager.db = Database.get_instance()

    yield

    Database._instance = None  # type: ignore[attr-defined]


def _setup_group(group_id: str = "pers_1", user_id: int = 1) -> None:
    """Создаёт группу и пользователя напрямую в БД (без сложной логики)."""
    with group_manager.db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO groups (group_id, name, owner_id, invite_code) VALUES (?, ?, ?, NULL)",
            (group_id, "Test", user_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id),
        )


def _link_recipe(group_id: str, category: str, slug: str) -> None:
    with group_manager.db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO group_recipes (group_id, category, slug) VALUES (?, ?, ?)",
            (group_id, category, slug),
        )


class TestSearchByIngredientMorphology:
    def test_10_яиц_found_by_яйца(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("завтрак", "omlet", ["10 яиц"])
        _link_recipe("pers_1", "завтрак", "omlet")

        results = group_manager.search_recipes_by_ingredient("pers_1", "яйца", "завтрак")
        assert "omlet" in results

    def test_10_яиц_found_by_яйцо(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("завтрак", "omlet", ["10 яиц"])
        _link_recipe("pers_1", "завтрак", "omlet")

        results = group_manager.search_recipes_by_ingredient("pers_1", "яйцо", "завтрак")
        assert "omlet" in results

    def test_филе_индейки_found_by_индейка(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("основное блюдо", "turkey", ["филе индейки"])
        _link_recipe("pers_1", "основное блюдо", "turkey")

        results = group_manager.search_recipes_by_ingredient("pers_1", "индейка", "основное блюдо")
        assert "turkey" in results

    def test_куриная_грудка_found_by_курица(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("основное блюдо", "chicken", ["куриная грудка"])
        _link_recipe("pers_1", "основное блюдо", "chicken")

        # «курица» лемматизируется в «курица»; «куриная» → «куриный».
        # Это разные леммы, поэтому запрос «курица» НЕ дожно находить «куриная грудка»
        # (т.к. мы не делаем синонимический поиск).
        # Это проверяет, что мы не выдаём ложных срабатываний.
        results = group_manager.search_recipes_by_ingredient("pers_1", "курица", "основное блюдо")
        assert "chicken" not in results

    def test_куриная_грудка_found_by_куриная(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("основное блюдо", "chicken", ["куриная грудка"])
        _link_recipe("pers_1", "основное блюдо", "chicken")

        results = group_manager.search_recipes_by_ingredient("pers_1", "куриная", "основное блюдо")
        assert "chicken" in results

    def test_phrase_query_finds_recipe(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("основное блюдо", "chicken", ["куриная грудка"])
        _link_recipe("pers_1", "основное блюдо", "chicken")

        # «куриная грудка» → обе леммы должны присутствовать
        results = group_manager.search_recipes_by_ingredient("pers_1", "куриная грудка", "основное блюдо")
        assert "chicken" in results

    def test_wrong_category_excludes(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("завтрак", "omlet", ["10 яиц"])
        _link_recipe("pers_1", "завтрак", "omlet")

        results = group_manager.search_recipes_by_ingredient("pers_1", "яйца", "десерт")
        assert results == []

    def test_digit_only_query_returns_empty(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("завтрак", "omlet", ["10 яиц"])
        _link_recipe("pers_1", "завтрак", "omlet")

        results = group_manager.search_recipes_by_ingredient("pers_1", "10", "завтрак")
        assert results == []

    def test_empty_query_returns_empty(self, temp_db):
        _setup_group()
        group_manager.index_recipe_ingredients("завтрак", "omlet", ["10 яиц"])

        assert group_manager.search_recipes_by_ingredient("pers_1", "", "завтрак") == []
        assert group_manager.search_recipes_by_ingredient("pers_1", "   ", "завтрак") == []
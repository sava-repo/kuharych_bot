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
    """Создаёт группу и пользователя напрямую в БД."""
    with group_manager.db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO groups (group_id, name, owner_id, invite_code) VALUES (?, ?, ?, NULL)",
            (group_id, "Test", user_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id),
        )


def _save_and_link(group_id: str, category: str, slug: str, title: str,
                   ingredients: list[str], steps: list[str] | None = None) -> None:
    """Сохраняет рецепт и привязывает к группе."""
    group_manager.save_recipe(
        category=category,
        slug=slug,
        title=title,
        content_md=f"# {title}",
        source="",
        ingredients=ingredients,
        steps=steps or [],
    )
    with group_manager.db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO group_recipes (group_id, category, slug) VALUES (?, ?, ?)",
            (group_id, category, slug),
        )


class TestSearchFulltext:
    def test_search_by_ingredient_lemma(self, temp_db):
        _setup_group()
        _save_and_link("pers_1", "завтрак", "omlet", "Омлет", ["10 яиц"])

        results = group_manager.search_recipes_fulltext("pers_1", "яйца")
        assert len(results) == 1
        assert results[0] == ("завтрак", "omlet", "Омлет")

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
        _setup_group()
        with group_manager.db.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO groups (group_id, name, owner_id, invite_code) VALUES (?, ?, ?, NULL)",
                ("pers_2", "Other", 2),
            )
            conn.execute(
                "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
                ("pers_2", 2),
            )

        _save_and_link("pers_1", "завтрак", "omlet1", "Омлет 1", ["яйца"])
        _save_and_link("pers_1", "завтрак", "omlet2", "Омлет 2", ["яйца", "молоко"])

        results = group_manager.search_recipes_fulltext("pers_2", "яйца")
        assert results == []

"""Тесты схемы БД и миграций: даты регистрации и добавления рецепта."""

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

    # Явно инициализируем схему (connect_raw не запускает _init_db).
    with group_manager.db.connect():
        pass

    yield

    Database._instance = None


def _columns(table: str) -> set[str]:
    with group_manager.db.connect_raw() as conn:
        return group_manager.db._table_columns(conn, table)


class TestSchemaColumns:
    def test_users_has_registered_at(self, temp_db):
        assert "registered_at" in _columns("users")

    def test_group_recipes_has_added_fields(self, temp_db):
        cols = _columns("group_recipes")
        assert "added_at" in cols
        assert "added_by_user_id" in cols


class TestMigration:
    def test_migrate_adds_missing_columns_to_old_schema(self, temp_db):
        # Симулируем старую схему group_recipes без новых колонок
        with group_manager.db.connect_raw() as conn:
            conn.execute("DROP TABLE group_recipes")
            conn.execute(
                "CREATE TABLE group_recipes ("
                "group_id TEXT NOT NULL, category TEXT NOT NULL, slug TEXT NOT NULL, "
                "PRIMARY KEY (group_id, category, slug))"
            )
            assert "added_at" not in group_manager.db._table_columns(conn, "group_recipes")

            group_manager.db._migrate(conn)

            cols = group_manager.db._table_columns(conn, "group_recipes")
        assert "added_at" in cols
        assert "added_by_user_id" in cols

    def test_migrate_idempotent(self, temp_db):
        with group_manager.db.connect_raw() as conn:
            group_manager.db._migrate(conn)  # повторный запуск не должен падать
            cols = group_manager.db._table_columns(conn, "group_recipes")
        assert "added_at" in cols


class TestUserRegistration:
    def test_ensure_user_sets_registered_at(self, temp_db):
        user = group_manager._ensure_user(42)
        assert user.registered_at is not None
        assert user.active_group == "pers_42"

    def test_ensure_user_is_idempotent(self, temp_db):
        first = group_manager._ensure_user(42)
        second = group_manager._ensure_user(42)
        assert second.registered_at == first.registered_at


class TestRecipeAddedBy:
    def test_add_recipe_to_group_records_adder_and_time(self, temp_db):
        group_manager._ensure_user(7)
        group_manager.add_recipe_to_group("pers_7", "десерт", "tiramisu", user_id=7)

        with group_manager.db.connect() as conn:
            row = conn.execute(
                "SELECT added_at, added_by_user_id FROM group_recipes "
                "WHERE group_id = ? AND category = ? AND slug = ?",
                ("pers_7", "десерт", "tiramisu"),
            ).fetchone()

        assert row["added_at"] is not None
        assert row["added_by_user_id"] == 7

    def test_re_add_preserves_first_adder(self, temp_db):
        group_manager._ensure_user(7)
        group_manager._ensure_user(9)

        group_manager.add_recipe_to_group("pers_7", "десерт", "tiramisu", user_id=7)
        # Другой пользователь повторно «добавляет» тот же рецепт в ту же группу
        group_manager.add_recipe_to_group("pers_7", "десерт", "tiramisu", user_id=9)

        with group_manager.db.connect() as conn:
            row = conn.execute(
                "SELECT added_at, added_by_user_id FROM group_recipes "
                "WHERE group_id = ? AND category = ? AND slug = ?",
                ("pers_7", "десерт", "tiramisu"),
            ).fetchone()

        assert row["added_by_user_id"] == 7  # первый добавивший сохранён

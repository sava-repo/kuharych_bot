"""Тесты схемы БД и миграций."""

from __future__ import annotations

import sqlite3
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

    def test_group_recipes_uses_recipe_id(self, temp_db):
        cols = _columns("group_recipes")
        assert "recipe_id" in cols
        assert "category_id" in cols
        assert "category" not in cols
        assert "slug" not in cols

    def test_recipes_has_recipe_id_pk(self, temp_db):
        assert "recipe_id" in _columns("recipes")

    def test_group_categories_table_exists(self, temp_db):
        cols = _columns("group_categories")
        assert {"category_id", "group_id", "name", "position", "is_default"} <= cols


# ── Тесты миграции table-rebuild ──────────────────────────────────────────


OLD_SCHEMA_SQL = """
CREATE TABLE users (user_id INTEGER PRIMARY KEY, active_group TEXT NOT NULL, registered_at TEXT);
CREATE TABLE groups (group_id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id INTEGER NOT NULL, invite_code TEXT);
CREATE TABLE group_members (group_id TEXT NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (group_id, user_id));
CREATE TABLE group_recipes (
    group_id TEXT NOT NULL, category TEXT NOT NULL, slug TEXT NOT NULL,
    added_at TEXT, added_by_user_id INTEGER,
    PRIMARY KEY (group_id, category, slug)
);
CREATE TABLE reel_index (reel_id TEXT PRIMARY KEY, category TEXT NOT NULL, slug TEXT NOT NULL);
CREATE TABLE recipe_ingredients (
    category TEXT NOT NULL, slug TEXT NOT NULL, ingredient TEXT NOT NULL,
    ingredient_lemmas TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (category, slug, ingredient)
);
CREATE TABLE recipes (
    category TEXT NOT NULL, slug TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '', content_md TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '', full_text_lemmas TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (category, slug)
);
"""


@pytest.fixture
def old_db(tmp_path: Path, monkeypatch) -> Path:
    """Создаёт БД со старой схемой + тестовыми данными, НЕ запуская миграцию."""
    db_path = tmp_path / "old_bot.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
    Database._instance = None

    conn = sqlite3.connect(str(db_path))
    conn.executescript(OLD_SCHEMA_SQL)
    # Группа и пользователь
    conn.execute("INSERT INTO groups (group_id, name, owner_id) VALUES ('pers_1', 'Личные', 1)")
    conn.execute("INSERT INTO users (user_id, active_group, registered_at) VALUES (1, 'pers_1', '2026-01-01')")
    conn.execute("INSERT INTO group_members (group_id, user_id) VALUES ('pers_1', 1)")
    # Два рецепта в разных категориях, но одинаковый slug+content → должны слиться
    conn.execute("INSERT INTO recipes (category, slug, title, content_md, source) VALUES "
                 "('завтрак', 'ovsyanka', 'Овсянка', 'MD_OVSYANKA', 'src1')")
    conn.execute("INSERT INTO recipes (category, slug, title, content_md, source) VALUES "
                 "('десерт', 'ovsyanka', 'Овсянка', 'MD_OVSYANKA', 'src1')")
    # Рецепт с уникальным slug
    conn.execute("INSERT INTO recipes (category, slug, title, content_md, source) VALUES "
                 "('основное блюдо', 'borshch', 'Борщ', 'MD_BORSHCH', 'src2')")
    # Рецепт в кастомной категории
    conn.execute("INSERT INTO recipes (category, slug, title, content_md, source) VALUES "
                 "('каша', 'mannaya', 'Манная каша', 'MD_MANNAYA', 'src3')")
    # Ингредиенты
    conn.execute("INSERT INTO recipe_ingredients (category, slug, ingredient, ingredient_lemmas) VALUES "
                 "('завтрак', 'ovsyanka', 'овёс', 'овёс')")
    conn.execute("INSERT INTO recipe_ingredients (category, slug, ingredient, ingredient_lemmas) VALUES "
                 "('десерт', 'ovsyanka', 'овёс', 'овёс')")  # дубликат после слияния
    conn.execute("INSERT INTO recipe_ingredients (category, slug, ingredient, ingredient_lemmas) VALUES "
                 "('основное блюдо', 'borshch', 'свёкла', 'свёкла')")
    conn.execute("INSERT INTO recipe_ingredients (category, slug, ingredient, ingredient_lemmas) VALUES "
                 "('каша', 'mannaya', 'манка', 'манка')")
    # Reel-индекс на один из рецептов
    conn.execute("INSERT INTO reel_index (reel_id, category, slug) VALUES ('REEL_X', 'завтрак', 'ovsyanka')")
    # group_recipes: ovsyanka (завтрак), mannanya (каша - кастомная), borshch (основное блюдо)
    conn.execute("INSERT INTO group_recipes (group_id, category, slug, added_at, added_by_user_id) VALUES "
                 "('pers_1', 'завтрак', 'ovsyanka', '2026-01-02', 1)")
    conn.execute("INSERT INTO group_recipes (group_id, category, slug, added_at, added_by_user_id) VALUES "
                 "('pers_1', 'каша', 'mannaya', '2026-01-03', 1)")
    conn.execute("INSERT INTO group_recipes (group_id, category, slug, added_at, added_by_user_id) VALUES "
                 "('pers_1', 'основное блюдо', 'borshch', '2026-01-04', 1)")
    conn.commit()
    conn.close()

    yield db_path

    Database._instance = None


def _run_migration() -> None:
    """Триггерит _init_db (миграцию) через новый Database."""
    db = Database.get_instance()
    group_manager.db = db
    with db.connect():
        pass


class TestRecipeIdMigration:
    def test_migration_runs_without_error(self, old_db):
        _run_migration()

    def test_recipes_deduped_by_slug(self, old_db):
        _run_migration()
        with group_manager.db.connect() as conn:
            rows = conn.execute("SELECT recipe_id, slug FROM recipes ORDER BY slug").fetchall()
        slugs = [r["slug"] for r in rows]
        # ovsyanka (слит из 2 категорий) + borshch + mannaya = 3 уникальных
        assert slugs == ["borshch", "mannaya", "ovsyanka"]

    def test_recipe_ingredients_deduped(self, old_db):
        _run_migration()
        with group_manager.db.connect() as conn:
            rows = conn.execute(
                "SELECT ingredient FROM recipe_ingredients WHERE recipe_id = "
                "(SELECT recipe_id FROM recipes WHERE slug='ovsyanka')"
            ).fetchall()
        # После слияния двух категорий остаётся один ингредиент 'овёс'
        assert len(rows) == 1

    def test_reel_index_migrated_to_recipe_id(self, old_db):
        _run_migration()
        with group_manager.db.connect() as conn:
            row = conn.execute("SELECT recipe_id FROM reel_index WHERE reel_id='REEL_X'").fetchone()
            recipe = conn.execute("SELECT slug FROM recipes WHERE recipe_id=?", (row["recipe_id"],)).fetchone()
        assert recipe["slug"] == "ovsyanka"

    def test_group_categories_seeded_with_defaults_and_custom(self, old_db):
        _run_migration()
        with group_manager.db.connect() as conn:
            cats = conn.execute(
                "SELECT name, is_default FROM group_categories WHERE group_id='pers_1' ORDER BY position"
            ).fetchall()
        names = [c["name"] for c in cats]
        # 3 дефолта + 1 кастомная ('каша')
        assert "завтрак" in names
        assert "основное блюдо" in names
        assert "десерт" in names
        assert "каша" in names
        # default помечен
        defaults = [c for c in cats if c["is_default"] == 1]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "основное блюдо"

    def test_group_recipes_use_recipe_id_and_category_id(self, old_db):
        _run_migration()
        with group_manager.db.connect() as conn:
            rows = conn.execute(
                "SELECT gr.recipe_id, gc.name AS category, r.slug "
                "FROM group_recipes gr "
                "JOIN group_categories gc ON gc.category_id = gr.category_id "
                "JOIN recipes r ON r.recipe_id = gr.recipe_id "
                "WHERE gr.group_id='pers_1' ORDER BY gc.name"
            ).fetchall()
        # ovsyanka в 'завтрак'; mannaya в 'каша'; borshch в 'основное блюдо'
        by_cat = {r["category"]: r["slug"] for r in rows}
        assert by_cat.get("завтрак") == "ovsyanka"
        assert by_cat.get("каша") == "mannaya"
        assert by_cat.get("основное блюдо") == "borshch"

    def test_migration_is_idempotent(self, old_db):
        _run_migration()
        # Повторная инициализация не должна ничего ломать
        Database._instance = None
        _run_migration()
        with group_manager.db.connect() as conn:
            cnt = conn.execute("SELECT COUNT(*) AS c FROM recipes").fetchone()["c"]
        assert cnt == 3


class TestUserRegistration:
    def test_ensure_user_sets_registered_at(self, temp_db):
        user = group_manager._ensure_user(42)
        assert user.registered_at is not None
        assert user.active_group == "pers_42"

    def test_ensure_user_is_idempotent(self, temp_db):
        first = group_manager._ensure_user(42)
        second = group_manager._ensure_user(42)
        assert second.registered_at == first.registered_at


class TestCategoryCRUD:
    """CRUD категорий: создать / переименовать / удалить + защита default."""

    def test_new_user_gets_default_categories(self, temp_db):
        group_manager._ensure_user(7)
        cats = group_manager.get_group_categories("pers_7")
        names = [c.name for c in cats]
        assert {"завтрак", "основное блюдо", "десерт"} == set(names)
        default = group_manager.get_default_category_id("pers_7")
        assert default is not None

    def test_create_category(self, temp_db):
        group_manager._ensure_user(7)
        cat = group_manager.create_category("pers_7", "супы")
        assert cat.name == "супы"
        assert cat.is_default is False
        assert group_manager.get_category("pers_7", "супы") is not None

    def test_create_duplicate_raises(self, temp_db):
        group_manager._ensure_user(7)
        group_manager.create_category("pers_7", "супы")
        with pytest.raises(group_manager.CategoryError):
            group_manager.create_category("pers_7", "супы")

    def test_rename_category_keeps_recipes(self, temp_db):
        group_manager._ensure_user(7)
        cat = group_manager.create_category("pers_7", "супы")
        rid = group_manager.save_recipe("borscht", "Борщ", "# Борщ", "", ["свёкла"], [])
        group_manager.add_recipe_to_group("pers_7", rid, cat.category_id, 7)

        group_manager.rename_category("pers_7", cat.category_id, "первые блюда")

        linked = group_manager.get_group_recipe_category("pers_7", rid)
        assert linked.name == "первые блюда"

    def test_delete_category_moves_recipes_to_default(self, temp_db):
        group_manager._ensure_user(7)
        cat = group_manager.create_category("pers_7", "супы")
        default_id = group_manager.get_default_category_id("pers_7")
        rid = group_manager.save_recipe("borscht", "Борщ", "# Борщ", "", ["свёкла"], [])
        group_manager.add_recipe_to_group("pers_7", rid, cat.category_id, 7)

        group_manager.delete_category("pers_7", cat.category_id)

        linked = group_manager.get_group_recipe_category("pers_7", rid)
        assert linked.category_id == default_id
        assert group_manager.get_category("pers_7", "супы") is None

    def test_cannot_delete_default_category(self, temp_db):
        group_manager._ensure_user(7)
        default_id = group_manager.get_default_category_id("pers_7")
        with pytest.raises(group_manager.CategoryError):
            group_manager.delete_category("pers_7", default_id)

    def test_rename_duplicate_name_raises(self, temp_db):
        group_manager._ensure_user(7)
        group_manager.create_category("pers_7", "супы")
        cat2 = group_manager.create_category("pers_7", "выпечка")
        with pytest.raises(group_manager.CategoryError):
            group_manager.rename_category("pers_7", cat2.category_id, "супы")


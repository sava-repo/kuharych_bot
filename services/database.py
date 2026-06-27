"""Управление подключением к SQLite с lazy-инициализацией."""

import logging
import sqlite3
from pathlib import Path

import config
from constants import DEFAULT_CATEGORIES

logger = logging.getLogger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    active_group TEXT NOT NULL,
    registered_at TEXT
);

CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    invite_code TEXT
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id TEXT NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS group_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    TEXT    NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    is_default  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (group_id, name)
);

CREATE TABLE IF NOT EXISTS recipes (
    recipe_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    slug             TEXT    NOT NULL,
    title            TEXT    NOT NULL DEFAULT '',
    content_md       TEXT    NOT NULL DEFAULT '',
    source           TEXT    NOT NULL DEFAULT '',
    full_text_lemmas TEXT    NOT NULL DEFAULT '',
    created          TEXT    NOT NULL DEFAULT '',
    UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id         INTEGER NOT NULL REFERENCES recipes(recipe_id) ON DELETE CASCADE,
    ingredient        TEXT    NOT NULL,
    ingredient_lemmas TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (recipe_id, ingredient)
);

CREATE TABLE IF NOT EXISTS reel_index (
    reel_id   TEXT    PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipes(recipe_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_recipes (
    group_id          TEXT    NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    recipe_id         INTEGER NOT NULL REFERENCES recipes(recipe_id) ON DELETE CASCADE,
    category_id       INTEGER NOT NULL REFERENCES group_categories(category_id),
    added_at          TEXT,
    added_by_user_id  INTEGER,
    PRIMARY KEY (group_id, recipe_id)
);
"""


class Database:
    """Lazy-init singleton для работы с SQLite."""

    _instance: "Database | None" = None

    def __init__(self) -> None:
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "Database":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _db_path(self) -> Path:
        p = Path(config.DATABASE_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def connect(self) -> sqlite3.Connection:
        """Создаёт новое подключение к БД (с WAL и foreign keys)."""
        if not self._initialized:
            self._init_db()
            self._initialized = True

        conn = sqlite3.connect(str(self._db_path()))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Создаёт таблицы, если их нет, и запускает миграции."""
        with self.connect_raw() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Идемпотентные миграции."""
        user_cols = self._table_columns(conn, "users")
        if "registered_at" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN registered_at TEXT")

        # Миграция со старой схемы (category в PK рецепта) на новую (recipe_id).
        recipes_cols = self._table_columns(conn, "recipes")
        if recipes_cols and "recipe_id" not in recipes_cols:
            logger.info("Detected pre-user-categories schema; running rebuild migration")
            self._migrate_recipes_to_recipe_id(conn)

    @staticmethod
    def _exec(conn: sqlite3.Connection, script: str) -> None:
        """Выполняет многооператорный SQL построчно (без executescript, который
        неявно COMMIT'ит и рвёт текущую транзакцию)."""
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)

    def _migrate_recipes_to_recipe_id(self, conn: sqlite3.Connection) -> None:
        """Перестраивает схему: отвязывает категорию от идентичности рецепта.

        Создаёт новые таблицы (recipes/recipe_ingredients/reel_index/group_recipes
        через recipe_id + category_id), сидирует group_categories для всех групп,
        переносит данные, затем дропает старые таблицы и переименовывает новые.
        Выполняется в одной транзакции с выключенными FK.
        """
        prev_isolation = conn.isolation_level
        conn.isolation_level = None  # ручное управление транзакцией
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")

            # ── 1. Новые таблицы (с временной суффиксацией, group_categories — финальное имя)
            self._exec(conn, """
                CREATE TABLE recipes_new (
                    recipe_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug             TEXT    NOT NULL,
                    title            TEXT    NOT NULL DEFAULT '',
                    content_md       TEXT    NOT NULL DEFAULT '',
                    source           TEXT    NOT NULL DEFAULT '',
                    full_text_lemmas TEXT    NOT NULL DEFAULT '',
                    created          TEXT    NOT NULL DEFAULT '',
                    UNIQUE (slug)
                )
            """)
            self._exec(conn, """
                CREATE TABLE recipe_ingredients_new (
                    recipe_id         INTEGER NOT NULL REFERENCES recipes_new(recipe_id) ON DELETE CASCADE,
                    ingredient        TEXT    NOT NULL,
                    ingredient_lemmas TEXT    NOT NULL DEFAULT '',
                    PRIMARY KEY (recipe_id, ingredient)
                )
            """)
            self._exec(conn, """
                CREATE TABLE reel_index_new (
                    reel_id   TEXT    PRIMARY KEY,
                    recipe_id INTEGER NOT NULL REFERENCES recipes_new(recipe_id) ON DELETE CASCADE
                )
            """)
            self._exec(conn, """
                CREATE TABLE group_recipes_new (
                    group_id          TEXT    NOT NULL,
                    recipe_id         INTEGER NOT NULL,
                    category_id       INTEGER NOT NULL,
                    added_at          TEXT,
                    added_by_user_id  INTEGER,
                    PRIMARY KEY (group_id, recipe_id)
                )
            """)

            # ── 2. recipes: дедуп по slug (слияние при одинаковом content_md,
            #    суффиксация -2/-3 при разном контенте с тем же slug)
            recipe_id_by_key: dict[tuple[str, str], int] = {}
            recipe_id_by_slug: dict[str, int] = {}    # slug -> recipe_id первого вхождения
            slug_content: dict[str, str] = {}          # slug -> content_md первого вхождения
            slug_ids: set[str] = set()                 # все занятые slug'и (включая суффиксы)
            next_recipe_id = 1

            rows = conn.execute(
                "SELECT category, slug, title, content_md, source, full_text_lemmas, created "
                "FROM recipes ORDER BY slug, category"
            ).fetchall()
            for row in rows:
                key = (row["category"], row["slug"])
                orig_slug = row["slug"]
                content_md = row["content_md"] or ""

                # Тот же slug и тот же контент — сливаем с уже созданным recipe_id
                if orig_slug in slug_content and slug_content[orig_slug] == content_md:
                    recipe_id_by_key[key] = recipe_id_by_slug[orig_slug]
                    continue

                new_slug = orig_slug
                if orig_slug in slug_content and slug_content[orig_slug] != content_md:
                    suffix = 2
                    while f"{orig_slug}-{suffix}" in slug_ids:
                        suffix += 1
                    new_slug = f"{orig_slug}-{suffix}"

                conn.execute(
                    "INSERT INTO recipes_new "
                    "(recipe_id, slug, title, content_md, source, full_text_lemmas, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (next_recipe_id, new_slug, row["title"], content_md,
                     row["source"], row["full_text_lemmas"], row["created"]),
                )
                recipe_id_by_key[key] = next_recipe_id
                recipe_id_by_slug[new_slug] = next_recipe_id
                slug_content[new_slug] = content_md
                slug_ids.add(new_slug)
                next_recipe_id += 1

            logger.info("Migration: %d unique recipes", len(recipe_id_by_key))

            # ── 3. recipe_ingredients
            ing_rows = conn.execute(
                "SELECT category, slug, ingredient, ingredient_lemmas FROM recipe_ingredients"
            ).fetchall()
            for row in ing_rows:
                rid = recipe_id_by_key.get((row["category"], row["slug"]))
                if rid is None:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO recipe_ingredients_new "
                    "(recipe_id, ingredient, ingredient_lemmas) VALUES (?, ?, ?)",
                    (rid, row["ingredient"], row["ingredient_lemmas"]),
                )

            # ── 4. reel_index
            reel_rows = conn.execute(
                "SELECT reel_id, category, slug FROM reel_index"
            ).fetchall()
            for row in reel_rows:
                rid = recipe_id_by_key.get((row["category"], row["slug"]))
                if rid is None:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO reel_index_new (reel_id, recipe_id) VALUES (?, ?)",
                    (row["reel_id"], rid),
                )

            # ── 5. group_categories: для каждой группы 3 дефолта + текстовые категории из group_recipes
            group_rows = conn.execute("SELECT group_id FROM groups").fetchall()
            # Текущие текстовые категории по группам
            text_cats: dict[str, list[str]] = {}
            gr_rows = conn.execute(
                "SELECT DISTINCT group_id, category FROM group_recipes"
            ).fetchall()
            for row in gr_rows:
                text_cats.setdefault(row["group_id"], []).append(row["category"])

            category_id_by_group_name: dict[tuple[str, str], int] = {}
            next_category_id = 1
            for grow in group_rows:
                gid = grow["group_id"]
                seen_names: set[str] = set()
                # Сначала дефолтные
                for default in DEFAULT_CATEGORIES:
                    name = default["name"]
                    conn.execute(
                        "INSERT INTO group_categories "
                        "(category_id, group_id, name, position, is_default) VALUES (?, ?, ?, ?, ?)",
                        (next_category_id, gid, name, default["position"],
                         1 if default.get("is_default") else 0),
                    )
                    category_id_by_group_name[(gid, name)] = next_category_id
                    seen_names.add(name)
                    next_category_id += 1
                # Затем пользовательские текстовые (не дефолтные)
                position = len(DEFAULT_CATEGORIES)
                for name in text_cats.get(gid, []):
                    if name in seen_names:
                        continue
                    conn.execute(
                        "INSERT INTO group_categories "
                        "(category_id, group_id, name, position, is_default) VALUES (?, ?, ?, ?, 0)",
                        (next_category_id, gid, name, position, ),
                    )
                    category_id_by_group_name[(gid, name)] = next_category_id
                    seen_names.add(name)
                    position += 1
                    next_category_id += 1

            logger.info("Migration: seeded categories for %d groups", len(group_rows))

            # ── 6. group_recipes → (group_id, recipe_id, category_id)
            grec_rows = conn.execute(
                "SELECT group_id, category, slug, added_at, added_by_user_id FROM group_recipes"
            ).fetchall()
            for row in grec_rows:
                rid = recipe_id_by_key.get((row["category"], row["slug"]))
                cid = category_id_by_group_name.get((row["group_id"], row["category"]))
                if rid is None or cid is None:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO group_recipes_new "
                    "(group_id, recipe_id, category_id, added_at, added_by_user_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (row["group_id"], rid, cid, row["added_at"], row["added_by_user_id"]),
                )

            # ── 7. Замена старых таблиц новыми
            self._exec(conn, """
                DROP TABLE group_recipes
            """)
            self._exec(conn, "DROP TABLE recipe_ingredients")
            self._exec(conn, "DROP TABLE reel_index")
            self._exec(conn, "DROP TABLE recipes")

            self._exec(conn, "ALTER TABLE recipes_new RENAME TO recipes")
            self._exec(conn, "ALTER TABLE recipe_ingredients_new RENAME TO recipe_ingredients")
            self._exec(conn, "ALTER TABLE reel_index_new RENAME TO reel_index")
            self._exec(conn, "ALTER TABLE group_recipes_new RENAME TO group_recipes")

            # Синхронизируем sqlite_sequence для AUTOINCREMENT
            conn.execute(
                "INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES ('recipes', ?)",
                (next_recipe_id - 1,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES ('group_categories', ?)",
                (next_category_id - 1,),
            )

            conn.execute("COMMIT")
            logger.info("Migration to recipe_id schema completed successfully")
        except Exception:
            conn.execute("ROLLBACK")
            logger.exception("Migration failed, rolled back")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.isolation_level = prev_isolation

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        """Возвращает множество имён колонок таблицы."""
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def connect_raw(self) -> sqlite3.Connection:
        """Подключение без row_factory (для DDL и миграций)."""
        conn = sqlite3.connect(str(self._db_path()))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

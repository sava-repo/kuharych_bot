"""Управление подключением к SQLite с lazy-инициализацией."""

import logging
import sqlite3
from pathlib import Path

import config

logger = logging.getLogger(__name__)


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
        """Создаёт таблицы, если их нет."""
        with self.connect_raw() as conn:
            conn.executescript("""
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

                CREATE TABLE IF NOT EXISTS group_recipes (
                    group_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    added_at TEXT,
                    added_by_user_id INTEGER,
                    PRIMARY KEY (group_id, category, slug)
                );

                CREATE TABLE IF NOT EXISTS reel_index (
                    reel_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    slug TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recipe_ingredients (
                    category TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    ingredient TEXT NOT NULL,
                    ingredient_lemmas TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (category, slug, ingredient)
                );

                CREATE TABLE IF NOT EXISTS recipes (
                    category TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    content_md TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    full_text_lemmas TEXT NOT NULL DEFAULT '',
                    created TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (category, slug)
                );
            """)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Idempotent-миграции: добавляет недостающие колонки в существующие таблицы."""
        user_cols = self._table_columns(conn, "users")
        if "registered_at" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN registered_at TEXT")

        gr_cols = self._table_columns(conn, "group_recipes")
        if "added_at" not in gr_cols:
            conn.execute("ALTER TABLE group_recipes ADD COLUMN added_at TEXT")
        if "added_by_user_id" not in gr_cols:
            conn.execute("ALTER TABLE group_recipes ADD COLUMN added_by_user_id INTEGER")

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        """Возвращает множество имён колонок таблицы."""
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def connect_raw(self) -> sqlite3.Connection:
        """Подключение без row_factory (для DDL и миграций)."""
        conn = sqlite3.connect(str(self._db_path()))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

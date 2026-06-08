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
                    active_group TEXT NOT NULL
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

    def connect_raw(self) -> sqlite3.Connection:
        """Подключение без row_factory (для DDL и миграций)."""
        conn = sqlite3.connect(str(self._db_path()))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

"""Управление подключением к SQLite с lazy-инициализацией.

Заменяет прямые вызовы sqlite3.connect() и side-effect при импорте.
"""

import json
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

                CREATE TABLE IF NOT EXISTS source_index (
                    source_url TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    slug TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recipe_ingredients (
                    category TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    ingredient TEXT NOT NULL,
                    PRIMARY KEY (category, slug, ingredient)
                );
            """)
        self._migrate_from_json()

    def connect_raw(self) -> sqlite3.Connection:
        """Подключение без row_factory (для DDL и миграций)."""
        conn = sqlite3.connect(str(self._db_path()))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _migrate_from_json(self) -> None:
        """Разовая миграция данных из JSON-файлов в SQLite."""
        data_dir = Path("data")
        users_file = data_dir / "users.json"
        groups_file = data_dir / "groups.json"
        group_recipes_file = data_dir / "group_recipes.json"
        source_index_file = data_dir / "source_index.json"

        if not users_file.exists() and not groups_file.exists():
            return

        logger.info("Migrating data from JSON to SQLite...")

        def _load_json(path: Path) -> dict:
            if not path.exists():
                return {}
            try:
                return json.loads(path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}

        users_data = _load_json(users_file)
        groups_data = _load_json(groups_file)
        group_recipes_data = _load_json(group_recipes_file)
        source_index_data = _load_json(source_index_file)

        with self.connect_raw() as conn:
            existing = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
            if existing > 0:
                logger.info("SQLite already has data, skipping migration")
                return

            for gid, gdata in groups_data.items():
                conn.execute(
                    "INSERT OR IGNORE INTO groups (group_id, name, owner_id, invite_code) VALUES (?, ?, ?, ?)",
                    (gid, gdata["name"], gdata["owner_id"], gdata.get("invite_code")),
                )
                for member_id in gdata.get("members", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
                        (gid, member_id),
                    )

            for uid_str, udata in users_data.items():
                conn.execute(
                    "INSERT OR IGNORE INTO users (user_id, active_group) VALUES (?, ?)",
                    (int(uid_str), udata.get("active_group", "")),
                )

            for gid, recipes in group_recipes_data.items():
                for recipe_key in recipes:
                    parts = recipe_key.split("/", 1)
                    if len(parts) == 2:
                        conn.execute(
                            "INSERT OR IGNORE INTO group_recipes (group_id, category, slug) VALUES (?, ?, ?)",
                            (gid, parts[0], parts[1]),
                        )

            for url, data in source_index_data.items():
                conn.execute(
                    "INSERT OR IGNORE INTO source_index (source_url, category, slug) VALUES (?, ?, ?)",
                    (url, data["category"], data["slug"]),
                )

        logger.info("Migration from JSON completed successfully")

        for f in [users_file, groups_file, group_recipes_file, source_index_file]:
            if f.exists():
                backup = f.with_suffix(".json.migrated")
                f.rename(backup)
                logger.info("Renamed %s -> %s", f.name, backup.name)
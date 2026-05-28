"""Управление пользователями, группами и связями с рецептами.

Хранилище — SQLite (data/bot.db).
Таблицы: users, groups, group_members, group_recipes, source_index.
"""

import json
import logging
import secrets
import sqlite3
from pathlib import Path

from models.group import Group, User

import config

logger = logging.getLogger(__name__)


# ── Подключение к БД ──────────────────────────────────────────────────

def _db_path() -> Path:
    p = Path(config.DATABASE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """Создаёт таблицы, если их нет."""
    with _connect() as conn:
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
    _migrate_from_json()


def _migrate_from_json() -> None:
    """Разовая миграция данных из JSON-файлов в SQLite."""
    data_dir = Path("data")
    users_file = data_dir / "users.json"
    groups_file = data_dir / "groups.json"
    group_recipes_file = data_dir / "group_recipes.json"
    source_index_file = data_dir / "source_index.json"

    if not users_file.exists() and not groups_file.exists():
        return  # Нет данных для миграции

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

    with _connect() as conn:
        # Проверяем, есть ли уже данные в БД
        existing = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        if existing > 0:
            logger.info("SQLite already has data, skipping migration")
            return

        # Мигрируем группы
        for gid, gdata in groups_data.items():
            conn.execute(
                "INSERT OR IGNORE INTO groups (group_id, name, owner_id, invite_code) VALUES (?, ?, ?, ?)",
                (gid, gdata["name"], gdata["owner_id"], gdata.get("invite_code")),
            )
            # Мигрируем участников
            for member_id in gdata.get("members", []):
                conn.execute(
                    "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
                    (gid, member_id),
                )

        # Мигрируем пользователей
        for uid_str, udata in users_data.items():
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, active_group) VALUES (?, ?)",
                (int(uid_str), udata.get("active_group", "")),
            )

        # Мигрируем рецепты групп
        for gid, recipes in group_recipes_data.items():
            for recipe_key in recipes:
                parts = recipe_key.split("/", 1)
                if len(parts) == 2:
                    conn.execute(
                        "INSERT OR IGNORE INTO group_recipes (group_id, category, slug) VALUES (?, ?, ?)",
                        (gid, parts[0], parts[1]),
                    )

        # Мигрируем индекс источников
        for url, data in source_index_data.items():
            conn.execute(
                "INSERT OR IGNORE INTO source_index (source_url, category, slug) VALUES (?, ?, ?)",
                (url, data["category"], data["slug"]),
            )

    logger.info("Migration from JSON completed successfully")

    # Переименовываем старые файлы
    for f in [users_file, groups_file, group_recipes_file, source_index_file]:
        if f.exists():
            backup = f.with_suffix(".json.migrated")
            f.rename(backup)
            logger.info(f"Renamed {f.name} -> {backup.name}")


# Инициализируем БД при импорте модуля
_init_db()


# ── Пользователи ──────────────────────────────────────────────────────

def _ensure_user(user_id: int) -> User:
    """Загружает пользователя, при отсутствии создаёт с личной группой."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT active_group FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if row:
            return User(user_id=user_id, active_group=row["active_group"])

        # Новый пользователь — создаём личную группу в той же транзакции
        personal_group_id = f"pers_{user_id}"
        _create_group_with_conn(conn, personal_group_id, "Личные рецепты", user_id, members=[user_id])

        conn.execute(
            "INSERT INTO users (user_id, active_group) VALUES (?, ?)",
            (user_id, personal_group_id),
        )

        logger.info(f"Created new user {user_id} with personal group {personal_group_id}")
        return User(user_id=user_id, active_group=personal_group_id)


def get_user_active_group(user_id: int) -> str:
    """Возвращает ID активной группы пользователя (создаёт пользователя если нужно)."""
    user = _ensure_user(user_id)
    return user.active_group


def set_user_active_group(user_id: int, group_id: str) -> bool:
    """Переключает активную группу пользователя."""
    with _connect() as conn:
        # Проверяем что пользователь существует
        row = conn.execute(
            "SELECT active_group FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        
        # Если пользователя нет — создаём в той же транзакции
        if not row:
            personal_group_id = f"pers_{user_id}"
            _create_group_with_conn(conn, personal_group_id, "Личные рецепты", user_id, members=[user_id])
            conn.execute(
                "INSERT INTO users (user_id, active_group) VALUES (?, ?)",
                (user_id, personal_group_id),
            )
            logger.info(f"Created user {user_id} during group switch")

        # Проверяем что группа существует и пользователь в ней
        group_row = conn.execute(
            "SELECT group_id FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if not group_row:
            return False

        member_row = conn.execute(
            "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        if not member_row:
            return False

        conn.execute(
            "UPDATE users SET active_group = ? WHERE user_id = ?",
            (group_id, user_id),
        )
        logger.info(f"User {user_id} switched to group {group_id}")
        return True


# ── Группы ────────────────────────────────────────────────────────────

def _create_group_with_conn(conn: sqlite3.Connection, group_id: str, name: str, owner_id: int, members: list[int] | None = None) -> Group:
    """Создаёт группу с использованием существующего соединения (для транзакций)."""
    members = members or [owner_id]

    conn.execute(
        "INSERT OR IGNORE INTO groups (group_id, name, owner_id, invite_code) VALUES (?, ?, ?, NULL)",
        (group_id, name, owner_id),
    )
    for mid in members:
        conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, mid),
        )

    return Group(group_id=group_id, name=name, owner_id=owner_id, members=members)


def _create_group(group_id: str, name: str, owner_id: int, members: list[int] | None = None) -> Group:
    """Создаёт группу (низкоуровневая, без проверок)."""
    with _connect() as conn:
        return _create_group_with_conn(conn, group_id, name, owner_id, members)


def create_custom_group(name: str, owner_id: int) -> Group:
    """Создаёт кастомную группу с уникальным ID."""
    with _connect() as conn:
        while True:
            code = secrets.token_hex(4)  # 8 символов
            group_id = f"grp_{code}"
            row = conn.execute(
                "SELECT group_id FROM groups WHERE group_id = ?", (group_id,)
            ).fetchone()
            if not row:
                break

    return _create_group(group_id, name, owner_id)


def get_group(group_id: str) -> Group | None:
    """Возвращает группу по ID."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT group_id, name, owner_id, invite_code FROM groups WHERE group_id = ?",
            (group_id,),
        ).fetchone()
        if not row:
            return None

        member_rows = conn.execute(
            "SELECT user_id FROM group_members WHERE group_id = ?",
            (group_id,),
        ).fetchall()
        members = [r["user_id"] for r in member_rows]

        return Group(
            group_id=row["group_id"],
            name=row["name"],
            owner_id=row["owner_id"],
            members=members,
            invite_code=row["invite_code"],
        )


def get_user_groups(user_id: int) -> list[Group]:
    """Возвращает все группы, в которых состоит пользователь."""
    _ensure_user(user_id)

    with _connect() as conn:
        rows = conn.execute(
            """SELECT g.group_id, g.name, g.owner_id, g.invite_code
               FROM groups g
               JOIN group_members gm ON g.group_id = gm.group_id
               WHERE gm.user_id = ?""",
            (user_id,),
        ).fetchall()

        result = []
        for row in rows:
            member_rows = conn.execute(
                "SELECT user_id FROM group_members WHERE group_id = ?",
                (row["group_id"],),
            ).fetchall()
            members = [r["user_id"] for r in member_rows]
            result.append(Group(
                group_id=row["group_id"],
                name=row["name"],
                owner_id=row["owner_id"],
                members=members,
                invite_code=row["invite_code"],
            ))
        return result


def generate_invite_code(group_id: str, owner_id: int) -> str | None:
    """Генерирует инвайт-код для группы (только для владельца)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT owner_id FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if not row or row["owner_id"] != owner_id:
            return None

        code = secrets.token_urlsafe(6)
        conn.execute(
            "UPDATE groups SET invite_code = ? WHERE group_id = ?",
            (code, group_id),
        )
        return code


def join_group_by_code(invite_code: str, user_id: int) -> Group | None:
    """Вступление в группу по инвайт-коду. Возвращает группу или None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT group_id FROM groups WHERE invite_code = ?",
            (invite_code,),
        ).fetchone()
        if not row:
            return None

        group_id = row["group_id"]

        # Проверяем, уже ли в группе
        existing = conn.execute(
            "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        if existing:
            return get_group(group_id)

        conn.execute(
            "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id),
        )
        logger.info(f"User {user_id} joined group {group_id}")
        return get_group(group_id)


def leave_group(group_id: str, user_id: int) -> bool:
    """Пользователь покидает группу. Владелец не может покинуть."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT owner_id FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if not row:
            return False
        if row["owner_id"] == user_id:
            return False  # Владелец не может выйти

        existing = conn.execute(
            "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        if not existing:
            return False

        conn.execute(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )

        # Если текущая активная группа — эта, переключаем на личную
        user_row = conn.execute(
            "SELECT active_group FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if user_row and user_row["active_group"] == group_id:
            personal = f"pers_{user_id}"
            conn.execute(
                "UPDATE users SET active_group = ? WHERE user_id = ?",
                (personal, user_id),
            )

        logger.info(f"User {user_id} left group {group_id}")
        return True


def rename_group(group_id: str, owner_id: int, new_name: str) -> bool:
    """Переименование группы (только владелец)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT owner_id FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if not row or row["owner_id"] != owner_id:
            return False
        conn.execute(
            "UPDATE groups SET name = ? WHERE group_id = ?",
            (new_name, group_id),
        )
        return True


# ── Связи группа↔рецепт ──────────────────────────────────────────────

def add_recipe_to_group(group_id: str, category: str, slug: str) -> None:
    """Добавляет рецепт в коллекцию группы."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO group_recipes (group_id, category, slug) VALUES (?, ?, ?)",
            (group_id, category, slug),
        )


def remove_recipe_from_group(group_id: str, category: str, slug: str) -> bool:
    """Удаляет рецепт из коллекции группы. Возвращает True если удалён."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM group_recipes WHERE group_id = ? AND category = ? AND slug = ?",
            (group_id, category, slug),
        )
        return cursor.rowcount > 0


def get_group_recipes(group_id: str) -> list[str]:
    """Возвращает список рецептов группы в формате 'категория/slug'."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category, slug FROM group_recipes WHERE group_id = ?",
            (group_id,),
        ).fetchall()
        return [f"{r['category']}/{r['slug']}" for r in rows]


def get_group_recipes_by_category(group_id: str, category: str) -> list[str]:
    """Возвращает slugs рецептов группы в конкретной категории."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT slug FROM group_recipes WHERE group_id = ? AND category = ?",
            (group_id, category),
        ).fetchall()
        return [r["slug"] for r in rows]


def recipe_exists_in_any_group(category: str, slug: str) -> bool:
    """Проверяет, существует ли рецепт хотя бы в одной группе."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM group_recipes WHERE category = ? AND slug = ? LIMIT 1",
            (category, slug),
        ).fetchone()
        return row is not None


# ── Индекс source URL → рецепт ────────────────────────────────────────

def find_recipe_by_source(source_url: str) -> dict | None:
    """Ищет рецепт по URL источника. Возвращает {category, slug} или None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT category, slug FROM source_index WHERE source_url = ?",
            (source_url,),
        ).fetchone()
        if not row:
            return None
        return {"category": row["category"], "slug": row["slug"]}


def register_source(source_url: str, category: str, slug: str) -> None:
    """Регистрирует связь source URL → рецепт."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO source_index (source_url, category, slug) VALUES (?, ?, ?)",
            (source_url, category, slug),
        )


def move_recipe_category(old_category: str, slug: str, new_category: str) -> int:
    """Обновляет категорию рецепта во ВСЕХ группах. Возвращает кол-во обновлённых записей."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE group_recipes SET category = ? WHERE category = ? AND slug = ?",
            (new_category, old_category, slug),
        )
        updated = cursor.rowcount
        if updated:
            # Обновляем категорию в индексе ингредиентов
            conn.execute(
                "UPDATE recipe_ingredients SET category = ? WHERE category = ? AND slug = ?",
                (new_category, old_category, slug),
            )
            logger.info(f"Moved recipe {slug}: {old_category} -> {new_category} in {updated} group(s)")
        return updated


def find_source_by_slug(category: str, slug: str) -> str | None:
    """Находит source_url по категории и slug."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT source_url FROM source_index WHERE category = ? AND slug = ?",
            (category, slug),
        ).fetchone()
        return row["source_url"] if row else None


def unregister_source(source_url: str) -> None:
    """Удаляет связь source URL → рецепт."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM source_index WHERE source_url = ?",
            (source_url,),
        )


# ── Индекс ингредиентов для поиска ─────────────────────────────────────

def index_recipe_ingredients(category: str, slug: str, ingredients: list[str]) -> None:
    """Индексирует ингредиенты рецепта для поиска."""
    with _connect() as conn:
        # Сначала удаляем старые ингредиенты (если есть)
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE category = ? AND slug = ?",
            (category, slug),
        )
        # Добавляем новые
        for ing in ingredients:
            conn.execute(
                "INSERT INTO recipe_ingredients (category, slug, ingredient) VALUES (?, ?, ?)",
                (category, slug, ing),
            )
        logger.debug(f"Indexed {len(ingredients)} ingredients for {category}/{slug}")


def remove_recipe_ingredients(category: str, slug: str) -> None:
    """Удаляет все ингредиенты рецепта из индекса."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE category = ? AND slug = ?",
            (category, slug),
        )
        logger.debug(f"Removed ingredients index for {category}/{slug}")


def search_recipes_by_ingredient(group_id: str, query: str, category: str) -> list[str]:
    """Ищет рецепты по ингредиенту в группе и категории. Возвращает список slugs."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT ri.slug
               FROM recipe_ingredients ri
               INNER JOIN group_recipes gr
                   ON gr.category = ri.category AND gr.slug = ri.slug
               WHERE ri.ingredient LIKE ?
                 AND gr.group_id = ?
                 AND ri.category = ?""",
            (f"%{query}%", group_id, category),
        ).fetchall()
        return [r["slug"] for r in rows]

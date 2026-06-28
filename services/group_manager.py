"""Управление пользователями, группами, категориями и рецептами.

Хранилище — SQLite (data/bot.db).
Категории принадлежат группе (group_categories). Рецепт идентифицируется
суррогатным recipe_id; категория рецепта — тег членства в группе (group_recipes).
"""

import logging
import secrets
from datetime import datetime, timezone

from constants import (
    DEFAULT_CATEGORIES,
    MAX_CATEGORIES_PER_GROUP,
    MAX_CATEGORY_NAME_LEN,
    MIN_CATEGORY_NAME_LEN,
)
from exceptions import CategoryError
from models.category import Category
from models.group import Group, User
from models.recipe import Recipe
from services import lemmatizer
from services.database import Database

logger = logging.getLogger(__name__)

db = Database.get_instance()


def _now_iso() -> str:
    """Текущее UTC-время в ISO-8601 (единый формат для timestamp-колонок)."""
    return datetime.now(timezone.utc).isoformat()


# ── Пользователи ──────────────────────────────────────────────────────

def _ensure_user(user_id: int) -> User:
    """Загружает пользователя, при отсутствии создаёт с личной группой."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT active_group, registered_at FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if row:
            return User(
                user_id=user_id,
                active_group=row["active_group"],
                registered_at=row["registered_at"],
            )

        personal_group_id = f"pers_{user_id}"
        _create_group_with_conn(conn, personal_group_id, "Личные рецепты", user_id, members=[user_id])

        registered_at = _now_iso()
        conn.execute(
            "INSERT INTO users (user_id, active_group, registered_at) VALUES (?, ?, ?)",
            (user_id, personal_group_id, registered_at),
        )

        logger.info("Created new user %s with personal group %s", user_id, personal_group_id)
        return User(
            user_id=user_id,
            active_group=personal_group_id,
            registered_at=registered_at,
        )


def get_user_active_group(user_id: int) -> str:
    """Возвращает ID активной группы пользователя (создаёт пользователя если нужно)."""
    user = _ensure_user(user_id)
    return user.active_group


def set_user_active_group(user_id: int, group_id: str) -> bool:
    """Переключает активную группу пользователя."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT active_group FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if not row:
            personal_group_id = f"pers_{user_id}"
            _create_group_with_conn(conn, personal_group_id, "Личные рецепты", user_id, members=[user_id])
            conn.execute(
                "INSERT INTO users (user_id, active_group, registered_at) VALUES (?, ?, ?)",
                (user_id, personal_group_id, _now_iso()),
            )
            logger.info("Created user %s during group switch", user_id)

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
        logger.info("User %s switched to group %s", user_id, group_id)
        return True


# ── Группы ────────────────────────────────────────────────────────────

def _seed_default_categories(conn, group_id: str) -> None:
    """Сидирует стандартный набор категорий для новой группы."""
    for default in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO group_categories (group_id, name, position, is_default) "
            "VALUES (?, ?, ?, ?)",
            (group_id, default["name"], default["position"],
             1 if default.get("is_default") else 0),
        )


def _create_group_with_conn(
    conn, group_id: str, name: str, owner_id: int, members: list[int] | None = None
) -> Group:
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
    _seed_default_categories(conn, group_id)

    return Group(group_id=group_id, name=name, owner_id=owner_id, members=members)


def _create_group(
    group_id: str, name: str, owner_id: int, members: list[int] | None = None
) -> Group:
    """Создаёт группу (низкоуровневая, без проверок)."""
    with db.connect() as conn:
        return _create_group_with_conn(conn, group_id, name, owner_id, members)


def create_custom_group(name: str, owner_id: int) -> Group:
    """Создаёт кастомную группу с уникальным ID."""
    with db.connect() as conn:
        while True:
            code = secrets.token_hex(4)
            group_id = f"grp_{code}"
            row = conn.execute(
                "SELECT group_id FROM groups WHERE group_id = ?", (group_id,)
            ).fetchone()
            if not row:
                break

    return _create_group(group_id, name, owner_id)


def get_group(group_id: str) -> Group | None:
    """Возвращает группу по ID."""
    with db.connect() as conn:
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

    with db.connect() as conn:
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
    with db.connect() as conn:
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
    with db.connect() as conn:
        row = conn.execute(
            "SELECT group_id FROM groups WHERE invite_code = ?",
            (invite_code,),
        ).fetchone()
        if not row:
            return None

        group_id = row["group_id"]

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
        logger.info("User %s joined group %s", user_id, group_id)
        return get_group(group_id)


def leave_group(group_id: str, user_id: int) -> bool:
    """Пользователь покидает группу. Владелец не может покинуть."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT owner_id FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if not row:
            return False
        if row["owner_id"] == user_id:
            return False

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

        user_row = conn.execute(
            "SELECT active_group FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if user_row and user_row["active_group"] == group_id:
            personal = f"pers_{user_id}"
            conn.execute(
                "UPDATE users SET active_group = ? WHERE user_id = ?",
                (personal, user_id),
            )

        logger.info("User %s left group %s", user_id, group_id)
        return True


def rename_group(group_id: str, owner_id: int, new_name: str) -> bool:
    """Переименование группы (только владелец)."""
    with db.connect() as conn:
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


# ── Категории (CRUD) ────────────────────────────────────────────────────

def _row_to_category(row) -> Category:
    return Category(
        category_id=row["category_id"],
        group_id=row["group_id"],
        name=row["name"],
        position=row["position"],
        is_default=bool(row["is_default"]),
    )


def get_group_categories(group_id: str) -> list[Category]:
    """Возвращает категории группы в порядке position."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT category_id, group_id, name, position, is_default "
            "FROM group_categories WHERE group_id = ? ORDER BY position, category_id",
            (group_id,),
        ).fetchall()
        return [_row_to_category(r) for r in rows]


def get_category_by_id(category_id: int) -> Category | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT category_id, group_id, name, position, is_default "
            "FROM group_categories WHERE category_id = ?",
            (category_id,),
        ).fetchone()
        return _row_to_category(row) if row else None


def get_category(group_id: str, name: str) -> Category | None:
    """Категория группы по имени (для резолва ответа LLM)."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT category_id, group_id, name, position, is_default "
            "FROM group_categories WHERE group_id = ? AND name = ?",
            (group_id, name),
        ).fetchone()
        return _row_to_category(row) if row else None


def get_default_category_id(group_id: str) -> int | None:
    """Возвращает category_id default-категории группы."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT category_id FROM group_categories WHERE group_id = ? AND is_default = 1",
            (group_id,),
        ).fetchone()
        return row["category_id"] if row else None


def create_category(group_id: str, name: str) -> Category:
    """Создаёт категорию в группе. Бросает CategoryError при дубликате/лимите."""
    name = (name or "").strip()
    if not (MIN_CATEGORY_NAME_LEN <= len(name) <= MAX_CATEGORY_NAME_LEN):
        raise CategoryError(
            f"Название категории должно быть от {MIN_CATEGORY_NAME_LEN} "
            f"до {MAX_CATEGORY_NAME_LEN} символов"
        )

    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM group_categories WHERE group_id = ?",
            (group_id,),
        ).fetchone()["c"]
        if count >= MAX_CATEGORIES_PER_GROUP:
            raise CategoryError(
                f"Достигнут лимит категорий ({MAX_CATEGORIES_PER_GROUP})"
            )

        existing = conn.execute(
            "SELECT 1 FROM group_categories WHERE group_id = ? AND name = ?",
            (group_id, name),
        ).fetchone()
        if existing:
            raise CategoryError(f"Категория «{name}» уже существует")

        cursor = conn.execute(
            "INSERT INTO group_categories (group_id, name, position, is_default) "
            "VALUES (?, ?, ?, 0)",
            (group_id, name, count),
        )
        category = Category(
            category_id=cursor.lastrowid,
            group_id=group_id,
            name=name,
            position=count,
            is_default=False,
        )
        logger.info("Created category %s in group %s", name, group_id)
        return category


def rename_category(group_id: str, category_id: int, new_name: str) -> None:
    """Переименовывает категорию. Бросает CategoryError при ошибках."""
    new_name = (new_name or "").strip()
    if not (MIN_CATEGORY_NAME_LEN <= len(new_name) <= MAX_CATEGORY_NAME_LEN):
        raise CategoryError(
            f"Название категории должно быть от {MIN_CATEGORY_NAME_LEN} "
            f"до {MAX_CATEGORY_NAME_LEN} символов"
        )

    with db.connect() as conn:
        dup = conn.execute(
            "SELECT 1 FROM group_categories WHERE group_id = ? AND name = ? "
            "AND category_id != ?",
            (group_id, new_name, category_id),
        ).fetchone()
        if dup:
            raise CategoryError(f"Категория «{new_name}» уже существует")

        cursor = conn.execute(
            "UPDATE group_categories SET name = ? "
            "WHERE category_id = ? AND group_id = ?",
            (new_name, category_id, group_id),
        )
        if cursor.rowcount == 0:
            raise CategoryError("Категория не найдена")
        logger.info("Renamed category %s -> %s", category_id, new_name)


def delete_category(group_id: str, category_id: int) -> None:
    """Удаляет категорию; рецепты переносятся в default-категорию.

    Бросает CategoryError при попытке удалить default или отсутствующую категорию.
    """
    with db.connect() as conn:
        row = conn.execute(
            "SELECT is_default FROM group_categories WHERE category_id = ? AND group_id = ?",
            (category_id, group_id),
        ).fetchone()
        if not row:
            raise CategoryError("Категория не найдена")
        if row["is_default"]:
            raise CategoryError("Категорию по умолчанию нельзя удалить")

        default = conn.execute(
            "SELECT category_id FROM group_categories WHERE group_id = ? AND is_default = 1",
            (group_id,),
        ).fetchone()
        if not default:
            raise CategoryError("В группе нет default-категории")

        conn.execute(
            "UPDATE group_recipes SET category_id = ? WHERE category_id = ? AND group_id = ?",
            (default["category_id"], category_id, group_id),
        )
        conn.execute(
            "DELETE FROM group_categories WHERE category_id = ? AND group_id = ?",
            (category_id, group_id),
        )
        logger.info("Deleted category %s in group %s", category_id, group_id)


# ── Связи группа↔рецепт ──────────────────────────────────────────────

def add_recipe_to_group(
    group_id: str, recipe_id: int, category_id: int, user_id: int
) -> None:
    """Добавляет рецепт в коллекцию группы под указанную категорию.

    Повторное добавление игнорируется (INSERT OR IGNORE) — категория/автор
    первого добавившего сохраняются.
    """
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO group_recipes "
            "(group_id, recipe_id, category_id, added_at, added_by_user_id) VALUES (?, ?, ?, ?, ?)",
            (group_id, recipe_id, category_id, _now_iso(), user_id),
        )


def remove_recipe_from_group(group_id: str, recipe_id: int) -> bool:
    """Удаляет рецепт из коллекции группы. Возвращает True если удалён."""
    with db.connect() as conn:
        cursor = conn.execute(
            "DELETE FROM group_recipes WHERE group_id = ? AND recipe_id = ?",
            (group_id, recipe_id),
        )
        return cursor.rowcount > 0


def get_group_recipes(group_id: str) -> list[int]:
    """Возвращает список recipe_id рецептов группы."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT recipe_id FROM group_recipes WHERE group_id = ?",
            (group_id,),
        ).fetchall()
        return [r["recipe_id"] for r in rows]


def get_group_recipes_by_category(group_id: str, category_id: int) -> list[int]:
    """Возвращает recipe_id рецептов группы в конкретной категории."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT recipe_id FROM group_recipes WHERE group_id = ? AND category_id = ?",
            (group_id, category_id),
        ).fetchall()
        return [r["recipe_id"] for r in rows]


def get_group_recipe_category(group_id: str, recipe_id: int) -> Category | None:
    """Категория, в которой рецепт находится в указанной группе."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT gc.category_id, gc.group_id, gc.name, gc.position, gc.is_default "
            "FROM group_recipes gr "
            "JOIN group_categories gc ON gc.category_id = gr.category_id "
            "WHERE gr.group_id = ? AND gr.recipe_id = ?",
            (group_id, recipe_id),
        ).fetchone()
        return _row_to_category(row) if row else None


def recipe_exists_in_any_group(recipe_id: int) -> bool:
    """Проверяет, существует ли рецепт хотя бы в одной группе."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM group_recipes WHERE recipe_id = ? LIMIT 1",
            (recipe_id,),
        ).fetchone()
        return row is not None


def recipe_in_group(group_id: str, recipe_id: int) -> bool:
    """Проверяет, есть ли рецепт в указанной группе."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM group_recipes WHERE group_id = ? AND recipe_id = ? LIMIT 1",
            (group_id, recipe_id),
        ).fetchone()
        return row is not None


def move_recipe_in_group(
    group_id: str, recipe_id: int, new_category_id: int
) -> bool:
    """Переносит рецепт в другую категорию В РАМКАХ ОДНОЙ группы.

    Не затрагивает другие группы (изоляция перемещения).
    """
    with db.connect() as conn:
        cursor = conn.execute(
            "UPDATE group_recipes SET category_id = ? "
            "WHERE group_id = ? AND recipe_id = ?",
            (new_category_id, group_id, recipe_id),
        )
        if cursor.rowcount:
            logger.info("Moved recipe %s in group %s to category_id %s",
                        recipe_id, group_id, new_category_id)
        return cursor.rowcount > 0


# ── Индекс reel ID → рецепт ─────────────────────────────────────────────

import re as _re

_REEL_ID_PATTERN = _re.compile(
    r"instagram\.com/reel(?:s)?/([A-Za-z0-9_-]+)", _re.IGNORECASE
)


def _extract_reel_id(url: str) -> str | None:
    """Извлекает reel ID из Instagram URL."""
    match = _REEL_ID_PATTERN.search(url)
    return match.group(1) if match else None


def find_recipe_by_source(url: str) -> int | None:
    """Ищет recipe_id по reel ID. Возвращает recipe_id или None."""
    reel_id = _extract_reel_id(url)
    if not reel_id:
        return None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT recipe_id FROM reel_index WHERE reel_id = ?",
            (reel_id,),
        ).fetchone()
        return row["recipe_id"] if row else None


def register_source(url: str, recipe_id: int) -> None:
    """Регистрирует связь reel ID → recipe_id."""
    reel_id = _extract_reel_id(url)
    if not reel_id:
        return
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reel_index (reel_id, recipe_id) VALUES (?, ?)",
            (reel_id, recipe_id),
        )


def unregister_source(url: str) -> None:
    """Удаляет связь reel ID → рецепт."""
    reel_id = _extract_reel_id(url)
    if not reel_id:
        return
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM reel_index WHERE reel_id = ?",
            (reel_id,),
        )


def find_source_by_slug(slug: str) -> str | None:
    """Находит полный URL рецепта по slug."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT source FROM recipes WHERE slug = ?",
            (slug,),
        ).fetchone()
        return row["source"] if row and row["source"] else None


def find_source_by_recipe_id(recipe_id: int) -> str | None:
    """Находит полный URL рецепта по recipe_id."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT source FROM recipes WHERE recipe_id = ?",
            (recipe_id,),
        ).fetchone()
        return row["source"] if row and row["source"] else None


# ── Индекс ингредиентов для поиска ─────────────────────────────────────

def index_recipe_ingredients(recipe_id: int, ingredients: list[str]) -> None:
    """Индексирует ингредиенты рецепта для поиска."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE recipe_id = ?",
            (recipe_id,),
        )
        for ing in ingredients:
            lemmas = lemmatizer.lemmatize_text(ing)
            conn.execute(
                "INSERT OR REPLACE INTO recipe_ingredients "
                "(recipe_id, ingredient, ingredient_lemmas) VALUES (?, ?, ?)",
                (recipe_id, ing, " ".join(lemmas)),
            )
        logger.debug("Indexed %s ingredients for recipe_id %s", len(ingredients), recipe_id)


def remove_recipe_ingredients(recipe_id: int) -> None:
    """Удаляет все ингредиенты рецепта из индекса."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE recipe_id = ?",
            (recipe_id,),
        )
        logger.debug("Removed ingredients index for recipe_id %s", recipe_id)


# ── CRUD рецептов (таблица recipes) ────────────────────────────────────

def save_recipe(
    slug: str,
    title: str,
    content_md: str,
    source: str,
    ingredients: list[str],
    steps: list[str],
    created: str = "",
) -> int:
    """Сохраняет рецепт в БД с полнотекстовой индексацией. Возвращает recipe_id.

    При совпадении slug обновляет существующую запись, сохраняя recipe_id
    (чтобы не ломать FK в recipe_ingredients/reel_index/group_recipes).
    """
    full_text = " ".join([title] + ingredients + steps)
    lemmas = lemmatizer.lemmatize_text(full_text)
    lemma_str = " ".join(lemmas)

    with db.connect() as conn:
        existing = conn.execute(
            "SELECT recipe_id FROM recipes WHERE slug = ?", (slug,)
        ).fetchone()
        if existing:
            recipe_id = existing["recipe_id"]
            conn.execute(
                "UPDATE recipes SET title = ?, content_md = ?, source = ?, "
                "full_text_lemmas = ?, created = ? WHERE recipe_id = ?",
                (title, content_md, source, lemma_str, created, recipe_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO recipes "
                "(slug, title, content_md, source, full_text_lemmas, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (slug, title, content_md, source, lemma_str, created),
            )
            recipe_id = cursor.lastrowid

    index_recipe_ingredients(recipe_id, ingredients)
    logger.info("Saved recipe %s (recipe_id=%s) to DB", slug, recipe_id)
    return recipe_id


def get_recipe(recipe_id: int) -> dict | None:
    """Возвращает рецепт из БД или None."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT recipe_id, slug, title, content_md, source, created "
            "FROM recipes WHERE recipe_id = ?",
            (recipe_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "recipe_id": row["recipe_id"],
            "slug": row["slug"],
            "title": row["title"],
            "content_md": row["content_md"],
            "source": row["source"],
            "created": row["created"],
        }


def get_recipe_by_slug(slug: str) -> dict | None:
    """Возвращает рецепт по slug."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT recipe_id, slug, title, content_md, source, created "
            "FROM recipes WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not row:
            return None
        return {
            "recipe_id": row["recipe_id"],
            "slug": row["slug"],
            "title": row["title"],
            "content_md": row["content_md"],
            "source": row["source"],
            "created": row["created"],
        }


def check_duplicate(slug: str) -> bool:
    """Проверяет наличие рецепта с таким slug."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM recipes WHERE slug = ? LIMIT 1",
            (slug,),
        ).fetchone()
        return row is not None


def delete_recipe(recipe_id: int) -> None:
    """Удаляет рецепт из БД полностью."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM recipes WHERE recipe_id = ?",
            (recipe_id,),
        )
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE recipe_id = ?",
            (recipe_id,),
        )
    logger.info("Deleted recipe_id %s from DB", recipe_id)


def save_recipe_as_new(recipe: Recipe) -> tuple[int, str]:
    """Сохраняет рецепт с суффиксом slug (-2, -3, ...). Возвращает (recipe_id, new_slug)."""
    suffix = 2
    base_slug = recipe.slug
    while check_duplicate(f"{base_slug}-{suffix}"):
        suffix += 1
    new_slug = f"{base_slug}-{suffix}"

    from dataclasses import replace
    new_recipe = replace(recipe, title=f"{recipe.title} ({suffix})")
    md_content = new_recipe.to_markdown(created="")

    recipe_id = save_recipe(
        slug=new_slug,
        title=new_recipe.title,
        content_md=md_content,
        source=new_recipe.source,
        ingredients=new_recipe.ingredients,
        steps=new_recipe.steps,
    )
    return recipe_id, new_slug


def overwrite_recipe(recipe: Recipe) -> int:
    """Перезаписывает существующий рецепт (по slug). Возвращает recipe_id."""
    md_content = recipe.to_markdown(created="")
    return save_recipe(
        slug=recipe.slug,
        title=recipe.title,
        content_md=md_content,
        source=recipe.source,
        ingredients=recipe.ingredients,
        steps=recipe.steps,
    )


def get_unindexed_recipes() -> list[int]:
    """Возвращает recipe_id, которые есть в group_recipes, но отсутствуют в recipes."""
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT gr.recipe_id
               FROM group_recipes gr
               LEFT JOIN recipes r ON r.recipe_id = gr.recipe_id
               WHERE r.recipe_id IS NULL"""
        ).fetchall()
        return [r["recipe_id"] for r in rows]


def get_all_recipe_slugs() -> list[tuple[int, str]]:
    """Возвращает все (recipe_id, slug) из таблицы recipes."""
    with db.connect() as conn:
        rows = conn.execute("SELECT recipe_id, slug FROM recipes").fetchall()
        return [(r["recipe_id"], r["slug"]) for r in rows]


def get_all_recipes_content() -> list[dict]:
    """Возвращает (recipe_id, content_md, created, source) всех рецептов.

    Используется бэкфиллом КБЖУ для перебора существующих рецептов.
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT recipe_id, content_md, created, source FROM recipes ORDER BY recipe_id"
        ).fetchall()
        return [
            {
                "recipe_id": r["recipe_id"],
                "content_md": r["content_md"],
                "created": r["created"],
                "source": r["source"],
            }
            for r in rows
        ]


def update_recipe_content_md(recipe_id: int, content_md: str) -> None:
    """Обновляет только content_md рецепта (для бэкфилла КБЖУ).

    Не затрагивает recipe_ingredients/reel_index/group_recipes и не переиндексирует
    леммы: КБЖУ хранится в frontmatter и не влияет на поиск.
    """
    with db.connect() as conn:
        conn.execute(
            "UPDATE recipes SET content_md = ? WHERE recipe_id = ?",
            (content_md, recipe_id),
        )


# ── Полнотекстовый поиск ──────────────────────────────────────────────

def search_recipes_fulltext(
    group_ids: str | list[str],
    query: str,
    *,
    prefer_group_id: str | None = None,
) -> list[tuple[int, str, str, str]]:
    """Ищет рецепты по всему тексту (название + ингредиенты + шаги).

    Поиск ведётся сразу по нескольким группам пользователя, чтобы смена
    активной группы не прятала рецепты, добавленные в другую группу.

    Возвращает список уникальных кортежей
    ``(recipe_id, slug, title, group_id)`` с дедупом по ``recipe_id``: если
    рецепт есть в нескольких из указанных групп, предпочтение отдаётся
    ``prefer_group_id`` (обычно активной группе), иначе — первой найденной.
    Результат сортируется по названию.

    ``group_ids`` принимает как одиночный id, так и список (одиночная строка
    нормализуется к списку — обратная совместимость).

    Поиск морфологически устойчив через лемматизацию pymorphy.
    """
    if not query or not query.strip():
        return []

    if isinstance(group_ids, str):
        group_ids = [group_ids]
    group_ids = [g for g in group_ids if g]
    if not group_ids:
        return []

    query_lemmas = lemmatizer.lemmatize_text(query)
    if not query_lemmas:
        return []

    lemma_clauses = " AND ".join(["r.full_text_lemmas LIKE ?"] * len(query_lemmas))
    group_placeholders = ", ".join(["?"] * len(group_ids))
    params = [f"%{lemma}%" for lemma in query_lemmas] + group_ids

    sql = f"""
        SELECT r.recipe_id, r.slug, r.title, gr.group_id
        FROM recipes r
        INNER JOIN group_recipes gr
            ON gr.recipe_id = r.recipe_id
        WHERE {lemma_clauses}
          AND gr.group_id IN ({group_placeholders})
    """

    with db.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    # Дедуп по recipe_id: prefer активной группы, иначе первая найденная.
    seen: dict[int, tuple[int, str, str, str]] = {}
    for r in rows:
        rid = r["recipe_id"]
        gid = r["group_id"]
        entry = (rid, r["slug"], r["title"], gid)
        existing = seen.get(rid)
        if existing is None:
            seen[rid] = entry
        elif (
            prefer_group_id is not None
            and existing[3] != prefer_group_id
            and gid == prefer_group_id
        ):
            seen[rid] = entry

    results = list(seen.values())
    results.sort(key=lambda x: x[2])
    return results

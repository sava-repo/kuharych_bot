"""Управление пользователями, группами и связями с рецептами.

Хранилище — SQLite (data/bot.db).
Таблицы: users, groups, group_members, group_recipes, source_index, recipe_ingredients, recipes.
"""

import logging
import secrets

from models.group import Group, User
from models.recipe import Recipe
from services import lemmatizer
from services.database import Database

logger = logging.getLogger(__name__)

db = Database.get_instance()


# ── Пользователи ──────────────────────────────────────────────────────

def _ensure_user(user_id: int) -> User:
    """Загружает пользователя, при отсутствии создаёт с личной группой."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT active_group FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if row:
            return User(user_id=user_id, active_group=row["active_group"])

        personal_group_id = f"pers_{user_id}"
        _create_group_with_conn(conn, personal_group_id, "Личные рецепты", user_id, members=[user_id])

        conn.execute(
            "INSERT INTO users (user_id, active_group) VALUES (?, ?)",
            (user_id, personal_group_id),
        )

        logger.info("Created new user %s with personal group %s", user_id, personal_group_id)
        return User(user_id=user_id, active_group=personal_group_id)


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
                "INSERT INTO users (user_id, active_group) VALUES (?, ?)",
                (user_id, personal_group_id),
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


# ── Связи группа↔рецепт ──────────────────────────────────────────────

def add_recipe_to_group(group_id: str, category: str, slug: str) -> None:
    """Добавляет рецепт в коллекцию группы."""
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO group_recipes (group_id, category, slug) VALUES (?, ?, ?)",
            (group_id, category, slug),
        )


def remove_recipe_from_group(group_id: str, category: str, slug: str) -> bool:
    """Удаляет рецепт из коллекции группы. Возвращает True если удалён."""
    with db.connect() as conn:
        cursor = conn.execute(
            "DELETE FROM group_recipes WHERE group_id = ? AND category = ? AND slug = ?",
            (group_id, category, slug),
        )
        return cursor.rowcount > 0


def get_group_recipes(group_id: str) -> list[str]:
    """Возвращает список рецептов группы в формате 'категория/slug'."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT category, slug FROM group_recipes WHERE group_id = ?",
            (group_id,),
        ).fetchall()
        return [f"{r['category']}/{r['slug']}" for r in rows]


def get_group_recipes_by_category(group_id: str, category: str) -> list[str]:
    """Возвращает slugs рецептов группы в конкретной категории."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT slug FROM group_recipes WHERE group_id = ? AND category = ?",
            (group_id, category),
        ).fetchall()
        return [r["slug"] for r in rows]


def recipe_exists_in_any_group(category: str, slug: str) -> bool:
    """Проверяет, существует ли рецепт хотя бы в одной группе."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM group_recipes WHERE category = ? AND slug = ? LIMIT 1",
            (category, slug),
        ).fetchone()
        return row is not None


# ── Индекс source URL → рецепт ────────────────────────────────────────

def find_recipe_by_source(source_url: str) -> dict | None:
    """Ищет рецепт по URL источника. Возвращает {category, slug} или None."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT category, slug FROM source_index WHERE source_url = ?",
            (source_url,),
        ).fetchone()
        if not row:
            return None
        return {"category": row["category"], "slug": row["slug"]}


def register_source(source_url: str, category: str, slug: str) -> None:
    """Регистрирует связь source URL → рецепт."""
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO source_index (source_url, category, slug) VALUES (?, ?, ?)",
            (source_url, category, slug),
        )


def move_recipe_category(old_category: str, slug: str, new_category: str) -> int:
    """Обновляет категорию рецепта во ВСЕХ группах. Возвращает кол-во обновлённых записей."""
    with db.connect() as conn:
        cursor = conn.execute(
            "UPDATE group_recipes SET category = ? WHERE category = ? AND slug = ?",
            (new_category, old_category, slug),
        )
        updated = cursor.rowcount
        if updated:
            conn.execute(
                "UPDATE recipe_ingredients SET category = ? WHERE category = ? AND slug = ?",
                (new_category, old_category, slug),
            )
            conn.execute(
                "UPDATE recipes SET category = ? WHERE category = ? AND slug = ?",
                (new_category, old_category, slug),
            )
            logger.info("Moved recipe %s: %s -> %s in %s group(s)", slug, old_category, new_category, updated)
        return updated


def find_source_by_slug(category: str, slug: str) -> str | None:
    """Находит source_url по категории и slug."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT source_url FROM source_index WHERE category = ? AND slug = ?",
            (category, slug),
        ).fetchone()
        return row["source_url"] if row else None


def unregister_source(source_url: str) -> None:
    """Удаляет связь source URL → рецепт."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM source_index WHERE source_url = ?",
            (source_url,),
        )


# ── Индекс ингредиентов для поиска ─────────────────────────────────────

def index_recipe_ingredients(category: str, slug: str, ingredients: list[str]) -> None:
    """Индексирует ингредиенты рецепта для поиска."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE category = ? AND slug = ?",
            (category, slug),
        )
        for ing in ingredients:
            lemmas = lemmatizer.lemmatize_text(ing)
            conn.execute(
                "INSERT OR REPLACE INTO recipe_ingredients "
                "(category, slug, ingredient, ingredient_lemmas) VALUES (?, ?, ?, ?)",
                (category, slug, ing, " ".join(lemmas)),
            )
        logger.debug("Indexed %s ingredients for %s/%s", len(ingredients), category, slug)


def remove_recipe_ingredients(category: str, slug: str) -> None:
    """Удаляет все ингредиенты рецепта из индекса."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE category = ? AND slug = ?",
            (category, slug),
        )
        logger.debug("Removed ingredients index for %s/%s", category, slug)


# ── CRUD рецептов (таблица recipes) ────────────────────────────────────

def save_recipe(
    category: str,
    slug: str,
    title: str,
    content_md: str,
    source: str,
    ingredients: list[str],
    steps: list[str],
    created: str = "",
) -> None:
    """Сохраняет рецепт в БД с полнотекстовой индексацией."""
    full_text = " ".join([title] + ingredients + steps)
    lemmas = lemmatizer.lemmatize_text(full_text)

    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO recipes "
            "(category, slug, title, content_md, source, full_text_lemmas, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (category, slug, title, content_md, source, " ".join(lemmas), created),
        )

    index_recipe_ingredients(category, slug, ingredients)
    logger.info("Saved recipe %s/%s to DB", category, slug)


def get_recipe(category: str, slug: str) -> dict | None:
    """Возвращает рецепт из БД или None."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT category, slug, title, content_md, source, created "
            "FROM recipes WHERE category = ? AND slug = ?",
            (category, slug),
        ).fetchone()
        if not row:
            return None
        return {
            "category": row["category"],
            "slug": row["slug"],
            "title": row["title"],
            "content_md": row["content_md"],
            "source": row["source"],
            "created": row["created"],
        }


def check_duplicate(category: str, slug: str) -> bool:
    """Проверяет наличие рецепта с таким slug в категории."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM recipes WHERE category = ? AND slug = ? LIMIT 1",
            (category, slug),
        ).fetchone()
        return row is not None


def delete_recipe(category: str, slug: str) -> None:
    """Удаляет рецепт из БД полностью."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM recipes WHERE category = ? AND slug = ?",
            (category, slug),
        )
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE category = ? AND slug = ?",
            (category, slug),
        )
    logger.info("Deleted recipe %s/%s from DB", category, slug)


def save_recipe_as_new(recipe: Recipe) -> str:
    """Сохраняет рецепт с суффиксом slug (-2, -3, ...). Возвращает новый slug."""
    suffix = 2
    base_slug = recipe.slug
    while check_duplicate(recipe.category, f"{base_slug}-{suffix}"):
        suffix += 1
    new_slug = f"{base_slug}-{suffix}"

    from dataclasses import replace
    new_recipe = replace(recipe, title=f"{recipe.title} ({suffix})")
    md_content = new_recipe.to_markdown(created="")

    save_recipe(
        category=new_recipe.category,
        slug=new_slug,
        title=new_recipe.title,
        content_md=md_content,
        source=new_recipe.source,
        ingredients=new_recipe.ingredients,
        steps=new_recipe.steps,
    )
    return new_slug


def overwrite_recipe(recipe: Recipe) -> None:
    """Перезаписывает существующий рецепт."""
    md_content = recipe.to_markdown(created="")
    save_recipe(
        category=recipe.category,
        slug=recipe.slug,
        title=recipe.title,
        content_md=md_content,
        source=recipe.source,
        ingredients=recipe.ingredients,
        steps=recipe.steps,
    )


def move_recipe(old_category: str, slug: str, new_category: str) -> None:
    """Перемещает рецепт в другую категорию."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT title, content_md, source, full_text_lemmas, created "
            "FROM recipes WHERE category = ? AND slug = ?",
            (old_category, slug),
        ).fetchone()
        if not row:
            return

        content_md = row["content_md"].replace(
            f"category: \"{old_category}\"",
            f"category: \"{new_category}\"",
        )

        conn.execute(
            "INSERT OR REPLACE INTO recipes "
            "(category, slug, title, content_md, source, full_text_lemmas, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_category, slug, row["title"], content_md, row["source"],
             row["full_text_lemmas"], row["created"]),
        )
        conn.execute(
            "DELETE FROM recipes WHERE category = ? AND slug = ?",
            (old_category, slug),
        )

    move_recipe_category(old_category, slug, new_category)
    logger.info("Moved recipe %s from %s to %s", slug, old_category, new_category)


def get_unindexed_recipes() -> list[tuple[str, str]]:
    """Возвращает (category, slug) из group_recipes, которых нет в таблице recipes."""
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT gr.category, gr.slug
               FROM group_recipes gr
               LEFT JOIN recipes r ON r.category = gr.category AND r.slug = gr.slug
               WHERE r.slug IS NULL"""
        ).fetchall()
        return [(r["category"], r["slug"]) for r in rows]


def get_all_recipe_slugs() -> list[tuple[str, str]]:
    """Возвращает все (category, slug) из таблицы recipes."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT category, slug FROM recipes"
        ).fetchall()
        return [(r["category"], r["slug"]) for r in rows]


# ── Полнотекстовый поиск ──────────────────────────────────────────────

def search_recipes_fulltext(group_id: str, query: str) -> list[tuple[str, str, str]]:
    """Ищет рецепты по всему тексту (название + ингредиенты + шаги).

    Возвращает список (category, slug, title) без ограничения по категории.
    Поиск морфологически устойчив через лемматизацию pymorphy.
    """
    if not query or not query.strip():
        return []

    query_lemmas = lemmatizer.lemmatize_text(query)
    if not query_lemmas:
        return []

    where_clauses = " AND ".join(["r.full_text_lemmas LIKE ?"] * len(query_lemmas))
    params = [f"%{lemma}%" for lemma in query_lemmas] + [group_id]

    sql = f"""
        SELECT r.category, r.slug, r.title
        FROM recipes r
        INNER JOIN group_recipes gr
            ON gr.category = r.category AND gr.slug = r.slug
        WHERE {where_clauses}
          AND gr.group_id = ?
        ORDER BY r.title
    """

    with db.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [(r["category"], r["slug"], r["title"]) for r in rows]

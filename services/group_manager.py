"""Управление пользователями, группами и связями с рецептами.

Хранилище — JSON-файлы в data/:
- users.json         — {user_id: {active_group: "..."}}
- groups.json        — {group_id: {name, owner_id, members, invite_code}}
- group_recipes.json — {group_id: ["кат/slugin1", "кат/slugin2"]}
- source_index.json  — {source_url: {category, slug}}
"""

import json
import logging
import secrets
from pathlib import Path
from typing import Any

from models.group import Group, User

import config

logger = logging.getLogger(__name__)


# ── Пути к файлам ─────────────────────────────────────────────────────

def _data_dir() -> Path:
    d = Path("data")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _users_path() -> Path:
    return _data_dir() / "users.json"


def _groups_path() -> Path:
    return _data_dir() / "groups.json"


def _group_recipes_path() -> Path:
    return _data_dir() / "group_recipes.json"


def _source_index_path() -> Path:
    return _data_dir() / "source_index.json"


# ── Общие утилиты для JSON ────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load {path}: {e}")
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


# ── Пользователи ──────────────────────────────────────────────────────

def _ensure_user(user_id: int) -> User:
    """Загружает пользователя, при отсутствии создаёт с личной группой."""
    users = _load_json(_users_path())
    key = str(user_id)

    if key in users:
        return User(user_id=user_id, active_group=users[key].get("active_group", ""))

    # Новый пользователь — создаём личную группу
    personal_group_id = f"pers_{user_id}"
    _create_group(personal_group_id, f"Личные рецепты", user_id, members=[user_id])

    user = User(user_id=user_id, active_group=personal_group_id)
    users[key] = {"active_group": personal_group_id}
    _save_json(_users_path(), users)

    logger.info(f"Created new user {user_id} with personal group {personal_group_id}")
    return user


def get_user_active_group(user_id: int) -> str:
    """Возвращает ID активной группы пользователя (создаёт пользователя если нужно)."""
    user = _ensure_user(user_id)
    return user.active_group


def set_user_active_group(user_id: int, group_id: str) -> bool:
    """Переключает активную группу пользователя."""
    users = _load_json(_users_path())
    key = str(user_id)

    # Убедимся что пользователь существует
    if key not in users:
        _ensure_user(user_id)
        users = _load_json(_users_path())

    # Проверяем что группа существует и пользователь в ней
    groups = _load_json(_groups_path())
    if group_id not in groups:
        return False
    if user_id not in groups[group_id].get("members", []):
        return False

    users[key]["active_group"] = group_id
    _save_json(_users_path(), users)
    logger.info(f"User {user_id} switched to group {group_id}")
    return True


# ── Группы ────────────────────────────────────────────────────────────

def _create_group(group_id: str, name: str, owner_id: int, members: list[int] | None = None) -> Group:
    """Создаёт группу (низкоуровневая, без проверок)."""
    groups = _load_json(_groups_path())
    group_data = {
        "name": name,
        "owner_id": owner_id,
        "members": members or [owner_id],
        "invite_code": None,
    }
    groups[group_id] = group_data
    _save_json(_groups_path(), groups)

    # Инициализируем пустой список рецептов
    gr = _load_json(_group_recipes_path())
    if group_id not in gr:
        gr[group_id] = []
        _save_json(_group_recipes_path(), gr)

    return Group(group_id=group_id, name=name, owner_id=owner_id, members=members or [owner_id])


def create_custom_group(name: str, owner_id: int) -> Group:
    """Создаёт кастомную группу с уникальным ID."""
    groups = _load_json(_groups_path())

    # Генерируем уникальный ID
    while True:
        code = secrets.token_hex(4)  # 8 символов
        group_id = f"grp_{code}"
        if group_id not in groups:
            break

    return _create_group(group_id, name, owner_id)


def get_group(group_id: str) -> Group | None:
    """Возвращает группу по ID."""
    groups = _load_json(_groups_path())
    if group_id not in groups:
        return None
    d = groups[group_id]
    return Group(
        group_id=group_id,
        name=d["name"],
        owner_id=d["owner_id"],
        members=d.get("members", []),
        invite_code=d.get("invite_code"),
    )


def get_user_groups(user_id: int) -> list[Group]:
    """Возвращает все группы, в которых состоит пользователь."""
    _ensure_user(user_id)
    groups_data = _load_json(_groups_path())
    result = []
    for gid, gdata in groups_data.items():
        if user_id in gdata.get("members", []):
            result.append(Group(
                group_id=gid,
                name=gdata["name"],
                owner_id=gdata["owner_id"],
                members=gdata.get("members", []),
                invite_code=gdata.get("invite_code"),
            ))
    return result


def generate_invite_code(group_id: str, owner_id: int) -> str | None:
    """Генерирует инвайт-код для группы (только для владельца)."""
    groups = _load_json(_groups_path())
    if group_id not in groups:
        return None
    if groups[group_id]["owner_id"] != owner_id:
        return None

    code = secrets.token_urlsafe(6)
    groups[group_id]["invite_code"] = code
    _save_json(_groups_path(), groups)
    return code


def join_group_by_code(invite_code: str, user_id: int) -> Group | None:
    """Вступление в группу по инвайт-коду. Возвращает группу или None."""
    groups = _load_json(_groups_path())

    for gid, gdata in groups.items():
        if gdata.get("invite_code") == invite_code:
            members = gdata.get("members", [])
            if user_id in members:
                return get_group(gid)  # Уже в группе
            members.append(user_id)
            gdata["members"] = members
            _save_json(_groups_path(), groups)
            logger.info(f"User {user_id} joined group {gid}")
            return get_group(gid)

    return None


def leave_group(group_id: str, user_id: int) -> bool:
    """Пользователь покидает группу. Владелец не может покинуть."""
    groups = _load_json(_groups_path())
    if group_id not in groups:
        return False
    gdata = groups[group_id]
    if gdata["owner_id"] == user_id:
        return False  # Владелец не может выйти
    if user_id not in gdata.get("members", []):
        return False

    gdata["members"].remove(user_id)
    _save_json(_groups_path(), groups)

    # Если текущая активная группа — эта, переключаем на личную
    users = _load_json(_users_path())
    key = str(user_id)
    if key in users and users[key].get("active_group") == group_id:
        personal = f"pers_{user_id}"
        users[key]["active_group"] = personal
        _save_json(_users_path(), users)

    logger.info(f"User {user_id} left group {group_id}")
    return True


def rename_group(group_id: str, owner_id: int, new_name: str) -> bool:
    """Переименование группы (только владелец)."""
    groups = _load_json(_groups_path())
    if group_id not in groups:
        return False
    if groups[group_id]["owner_id"] != owner_id:
        return False
    groups[group_id]["name"] = new_name
    _save_json(_groups_path(), groups)
    return True


# ── Связи группа↔рецепт ──────────────────────────────────────────────

def add_recipe_to_group(group_id: str, category: str, slug: str) -> None:
    """Добавляет рецепт в коллекцию группы."""
    gr = _load_json(_group_recipes_path())
    if group_id not in gr:
        gr[group_id] = []
    key = f"{category}/{slug}"
    if key not in gr[group_id]:
        gr[group_id].append(key)
        _save_json(_group_recipes_path(), gr)


def remove_recipe_from_group(group_id: str, category: str, slug: str) -> bool:
    """Удаляет рецепт из коллекции группы. Возвращает True если удалён."""
    gr = _load_json(_group_recipes_path())
    if group_id not in gr:
        return False
    key = f"{category}/{slug}"
    if key in gr[group_id]:
        gr[group_id].remove(key)
        _save_json(_group_recipes_path(), gr)
        return True
    return False


def get_group_recipes(group_id: str) -> list[str]:
    """Возвращает список рецептов группы в формате 'категория/slug'."""
    gr = _load_json(_group_recipes_path())
    return gr.get(group_id, [])


def get_group_recipes_by_category(group_id: str, category: str) -> list[str]:
    """Возвращает slugs рецептов группы в конкретной категории."""
    recipes = get_group_recipes(group_id)
    prefix = f"{category}/"
    return [r[len(prefix):] for r in recipes if r.startswith(prefix)]


def recipe_exists_in_any_group(category: str, slug: str) -> bool:
    """Проверяет, существует ли рецепт хотя бы в одной группе."""
    gr = _load_json(_group_recipes_path())
    key = f"{category}/{slug}"
    for group_id, recipes in gr.items():
        if key in recipes:
            return True
    return False


# ── Индекс source URL → рецепт ────────────────────────────────────────

def find_recipe_by_source(source_url: str) -> dict | None:
    """Ищет рецепт по URL источника. Возвращает {category, slug} или None."""
    idx = _load_json(_source_index_path())
    return idx.get(source_url)


def register_source(source_url: str, category: str, slug: str) -> None:
    """Регистрирует связь source URL → рецепт."""
    idx = _load_json(_source_index_path())
    idx[source_url] = {"category": category, "slug": slug}
    _save_json(_source_index_path(), idx)


def unregister_source(source_url: str) -> None:
    """Удаляет связь source URL → рецепт."""
    idx = _load_json(_source_index_path())
    idx.pop(source_url, None)
    _save_json(_source_index_path(), idx)
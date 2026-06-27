"""Rotation-система: исключает недавно показанные рецепты из случайного выбора.

Хранилище: in-memory dict с deque.
Ключ: (user_id, category_id) → deque[int] (recipe_id).
Данные теряются при перезапуске бота — приемлемо для UX-фичи.
"""

import logging
from collections import deque

logger = logging.getLogger(__name__)

# (user_id, category_id) → deque[int]
_rotation: dict[tuple[int, int], deque[int]] = {}


def add(user_id: int, category_id: int, recipe_id: int, total_count: int) -> None:
    """Добавляет recipe_id в rotation для (user_id, category_id).

    Автоматически ресайзит deque: maxlen = max(total_count - 1, 0).
    Если deque с таким maxlen уже существует — просто добавляет.
    Если total_count изменился — пересоздаёт deque с новым maxlen.
    """
    key = (user_id, category_id)
    new_maxlen = max(total_count - 1, 0)

    existing = _rotation.get(key)

    if existing is not None and existing.maxlen == new_maxlen:
        # Тот же размер — просто добавляем
        existing.append(recipe_id)
    else:
        # Пересоздаём с новым maxlen, сохраняя старые элементы
        old_items = list(existing) if existing is not None else []
        new_deque = deque(old_items, maxlen=new_maxlen)
        new_deque.append(recipe_id)
        _rotation[key] = new_deque

    logger.debug(
        f"Rotation add: user={user_id}, cat_id={category_id}, "
        f"recipe_id={recipe_id}, total={total_count}, maxlen={new_maxlen}"
    )


def get_excluded(user_id: int, category_id: int) -> list[int]:
    """Возвращает список recipe_id, исключённых из rotation."""
    key = (user_id, category_id)
    d = _rotation.get(key)
    if not d:
        return []
    return list(d)


def clear(user_id: int, category_id: int) -> None:
    """Сбрасывает rotation для (user_id, category_id)."""
    key = (user_id, category_id)
    if key in _rotation:
        del _rotation[key]
        logger.debug(f"Rotation cleared: user={user_id}, cat_id={category_id}")


def get_stats() -> dict:
    """Возвращает статистику rotation (для отладки)."""
    return {
        "entries": len(_rotation),
        "details": {
            f"uid={k[0]},cid={k[1]}": list(v) for k, v in _rotation.items()
        },
    }

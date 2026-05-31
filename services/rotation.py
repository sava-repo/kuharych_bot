"""Rotation-система: исключает недавно показанные рецепты из случайного выбора.

Хранилище: in-memory dict с deque.
Ключ: (user_id, category) → deque[str] (slug'ы).
Данные теряются при перезапуске бота — приемлемо для UX-фичи.
"""

import logging
from collections import deque

logger = logging.getLogger(__name__)

# (user_id, category) → deque[str]
_rotation: dict[tuple[int, str], deque[str]] = {}


def add(user_id: int, category: str, slug: str, total_count: int) -> None:
    """Добавляет slug в rotation для (user_id, category).

    Автоматически ресайзит deque: maxlen = max(total_count - 1, 0).
    Если deque с таким maxlen уже существует — просто добавляет.
    Если total_count изменился — пересоздаёт deque с новым maxlen.
    """
    key = (user_id, category)
    new_maxlen = max(total_count - 1, 0)

    existing = _rotation.get(key)

    if existing is not None and existing.maxlen == new_maxlen:
        # Тот же размер — просто добавляем
        existing.append(slug)
    else:
        # Пересоздаём с новым maxlen, сохраняя старые элементы
        old_items = list(existing) if existing is not None else []
        new_deque = deque(old_items, maxlen=new_maxlen)
        new_deque.append(slug)
        _rotation[key] = new_deque

    logger.debug(
        f"Rotation add: user={user_id}, cat={category}, slug={slug}, "
        f"total={total_count}, maxlen={new_maxlen}"
    )


def get_excluded(user_id: int, category: str) -> list[str]:
    """Возвращает список slug'ов, исключённых из rotation."""
    key = (user_id, category)
    d = _rotation.get(key)
    if not d:
        return []
    return list(d)


def clear(user_id: int, category: str) -> None:
    """Сбрасывает rotation для (user_id, category)."""
    key = (user_id, category)
    if key in _rotation:
        del _rotation[key]
        logger.debug(f"Rotation cleared: user={user_id}, cat={category}")


def get_stats() -> dict:
    """Возвращает статистику rotation (для отладки)."""
    return {
        "entries": len(_rotation),
        "details": {
            f"uid={k[0]},cat={k[1]}": list(v) for k, v in _rotation.items()
        },
    }
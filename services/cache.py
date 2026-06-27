"""In-memory LRU-кэш с TTL для хранения временных данных рецептов

Используется для callback_data кнопок Telegram — хранит данные рецепта
между отправкой сообщения и нажатием кнопки.
"""

import time
import logging

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 500
CACHE_TTL_SEC = 3600  # 1 час

# key -> (data, timestamp)
_cache: dict[str, tuple[dict, float]] = {}

# Счётчик для генерации уникальных ключей
_counter = 0

# Отдельный счётчик для рецептов (/open{key}) — начинается с 10000
_recipe_counter = 10000


def put(data: dict) -> str:
    """
    Сохраняет данные в кэш, возвращает короткий ключ (r0, r1, r2, ...).
    
    Args:
        data: словарь с данными (category, slug, sha, recipe и т.д.)
    
    Returns:
        Ключ для доступа к данным
    """
    global _counter
    _evict_if_needed()
    
    key = f"r{_counter}"
    _counter += 1
    _cache[key] = (data, time.time())
    
    logger.debug(f"Cache put: {key}, data keys: {list(data.keys())}")
    return key


def get(key: str) -> dict | None:
    """
    Получает данные по ключу. Возвращает None если ключ не найден или данные устарели.
    
    Args:
        key: ключ полученный из put()
    
    Returns:
        Словарь с данными или None
    """
    entry = _cache.get(key)
    if not entry:
        logger.debug(f"Cache miss: {key}")
        return None
    
    data, ts = entry
    age = time.time() - ts
    
    if age > CACHE_TTL_SEC:
        logger.debug(f"Cache expired: {key} (age={age:.0f}s)")
        del _cache[key]
        return None
    
    logger.debug(f"Cache hit: {key} (age={age:.0f}s)")
    return data


def update(key: str, data: dict) -> None:
    """
    Обновляет данные по ключу. Обновляет timestamp.
    
    Args:
        key: ключ полученный из put()
        data: новые данные
    """
    if key in _cache:
        _cache[key] = (data, time.time())
        logger.debug(f"Cache update: {key}")
    else:
        logger.warning(f"Cache update: key {key} not found")


def delete(key: str) -> None:
    """
    Удаляет данные по ключу.
    
    Args:
        key: ключ для удаления
    """
    if key in _cache:
        del _cache[key]
        logger.debug(f"Cache delete: {key}")


def put_recipe(recipe_id: int, group_id: str | None = None) -> int:
    """
    Сохраняет рецепт в кэш с числовым ключом (от 10000).
    Возвращает числовой ID для использования в /open{key}.
    """
    global _recipe_counter
    _evict_if_needed()
    key = str(_recipe_counter)
    _cache[key] = ({"recipe_id": recipe_id, "group_id": group_id}, time.time())
    _recipe_counter += 1
    logger.debug(f"Cache put_recipe: {key}, recipe_id={recipe_id}, group_id={group_id}")
    return _recipe_counter - 1


def clear() -> None:
    """Очищает весь кэш. Используется в тестах."""
    global _counter, _recipe_counter
    _cache.clear()
    _counter = 0
    _recipe_counter = 10000
    logger.debug("Cache cleared")


def get_stats() -> dict:
    """Возвращает статистику кэша."""
    now = time.time()
    entries = [{"key": k, "age": now - ts} for k, (_, ts) in _cache.items()]
    
    return {
        "size": len(_cache),
        "max_size": MAX_CACHE_SIZE,
        "counter": _counter,
        "oldest_age": max([e["age"] for e in entries]) if entries else 0,
        "newest_age": min([e["age"] for e in entries]) if entries else 0,
    }


def _evict_if_needed() -> None:
    """
    Удаляет просроченные и самые старые записи при переполнении.
    """
    now = time.time()
    
    # Удаляем просроченные записи
    expired_keys = [
        k for k, (_, ts) in _cache.items()
        if now - ts > CACHE_TTL_SEC
    ]
    for k in expired_keys:
        del _cache[k]
    
    if expired_keys:
        logger.debug(f"Evicted {len(expired_keys)} expired entries")
    
    # Если всё ещё переполнен — удаляем самые старые
    while len(_cache) >= MAX_CACHE_SIZE:
        oldest_key = min(_cache, key=lambda k: _cache[k][1])
        del _cache[oldest_key]
        logger.debug(f"Evicted oldest key: {oldest_key}")
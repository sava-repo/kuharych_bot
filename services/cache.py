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


def clear() -> None:
    """Очищает весь кэш (утилита для тестов/эксплуатации)."""
    global _counter
    _cache.clear()
    _counter = 0
    logger.debug("Cache cleared")


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
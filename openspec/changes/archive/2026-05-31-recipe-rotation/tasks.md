## 1. Rotation-модуль

- [x] 1.1 Создать `services/rotation.py` с in-memory хранилищем `dict[tuple[int, str], deque[str]]`
- [x] 1.2 Реализовать функцию `add(user_id, category, slug, total_count)` — добавляет slug в deque, при необходимости ресайзит
- [x] 1.3 Реализовать функцию `get_excluded(user_id, category) -> list[str]` — возвращает список исключённых slug'ов
- [x] 1.4 Реализовать функцию `clear(user_id, category)` — сбрасывает rotation для ключа
- [x] 1.5 Добавить логику автоматического ресайза deque: `maxlen = max(total_count - 1, 0)`

## 2. Интеграция в handlers/menu.py

- [x] 2.1 Добавить параметр `exclude: list[str] | None = None` в `_try_get_random_recipe` и `_try_get_recipe_from_slugs`
- [x] 2.2 Реализовать фильтрацию: `slugs = [s for s in slugs if s not in exclude_set]` перед `random.shuffle`
- [x] 2.3 Обновить `handle_menu_category` — получить `exclude` из rotation, вызвать `rotation.add()` после показа
- [x] 2.4 Обновить `handle_random_callback` — получить `exclude` из rotation, вызвать `rotation.add()` после показа
- [x] 2.5 Обновить `handle_search_category` — получить `exclude` из rotation, вызвать `rotation.add()` после показа
- [x] 2.6 Обновить `handle_search_random` — получить `exclude` из rotation, вызвать `rotation.add()` после показа

## 3. Edge cases

- [x] 3.1 Убедиться что при 0 доступных рецептах после фильтрации fallback на полный список (сброс rotation)
- [x] 3.2 Убедиться что при 1 рецепте в категории repeat допустим (deque maxlen = 0)
# Tasks: user-categories

## 1. Схема и миграция
**Файлы:** `services/database.py`

- [x] 1.1 Реализовать target-схему в `_init_db`: `group_categories`, `recipes` с `recipe_id` PK + UNIQUE-индекс `idx_recipes_slug`, `recipe_ingredients`/`reel_index`/`group_recipes` через `recipe_id`/`category_id`
- [x] 1.2 Реализовать `_migrate`: детект старой схемы (нет `recipe_id`), table-rebuild в одной транзакции
- [x] 1.3 Дедуп `recipes` по `slug` (слияние при одинаковом `content_md`, суффиксация `-2/-3` при разном)
- [x] 1.4 Перенос `recipe_ingredients` и `reel_index` на `recipe_id`
- [x] 1.5 Сидирование `group_categories` для всех существующих групп (3 дефолта + текстовые категории из `group_recipes`)
- [x] 1.6 Перевод `group_recipes` на `(group_id, recipe_id, category_id)` с маппингом текста категории → `category_id`
- [x] 1.7 Логирование хода миграции; идемпотентность (повторный запуск не падает на новой схеме)

## 2. Сервисный слой
**Файлы:** `services/group_manager.py`

- [x] 2.1 CRUD категорий: `create_category`, `rename_category`, `delete_category` (защита default + перенос рецептов в default), `get_group_categories`, `get_default_category_id`, `get_category_by_id`
- [x] 2.2 Сидирование дефолтных категорий в `_create_group_with_conn`
- [x] 2.3 Переписать recipe-функции под `recipe_id`: `save_recipe` (без category), `get_recipe(recipe_id)`, `check_duplicate(slug)`, `delete_recipe(recipe_id)`, `save_recipe_as_new`, `overwrite_recipe`
- [x] 2.4 `add_recipe_to_group(group_id, recipe_id, category_id, user_id)`, `remove_recipe_from_group(group_id, recipe_id)`, `get_group_recipes_by_category` (через category_id), `get_group_recipe_category(group_id, recipe_id)`, `recipe_exists_in_any_group(recipe_id)`
- [x] 2.5 Заменить глобальные move-функции на `move_recipe_in_group(group_id, recipe_id, new_category_id)`
- [x] 2.6 `register_source(url, recipe_id)`, `find_recipe_by_source(url) → recipe_id | None`
- [x] 2.7 `index_recipe_ingredients(recipe_id, ...)`, `remove_recipe_ingredients(recipe_id)`
- [x] 2.8 `search_recipes_fulltext` — JOIN через `recipe_id`
- [x] 2.9 `get_unindexed_recipes`, `get_all_recipe_slugs` — адаптировать под `recipe_id`

## 3. LLM-парсер
**Файлы:** `prompts/system.txt`, `services/recipe_parser.py`

- [x] 3.1 Превратить `system.txt` в шаблон с `{categories}` / `{default}`
- [x] 3.2 `generate_recipe(..., categories: list[str], default: str)` — сборка промпта
- [x] 3.3 `_parse_recipe_response` — матчинг категории против переданного списка, fallback на default
- [x] 3.4 Тесты `tests/unit/test_parser.py`: выбор из произвольного списка, fallback

## 4. Пайплайн
**Файлы:** `services/recipe_pipeline.py`

- [x] 4.1 Загрузка категорий группы, передача в `generate_recipe`, резолв ответа LLM в `category_id` (мимо → default)
- [x] 4.2 `_handle_existing_recipe`: добавление в новую группу под default-категорию
- [x] 4.3 Работа через `recipe_id` во всём пайплайне

## 5. In-memory сервисы
**Файлы:** `services/cache.py`, `services/rotation.py`

- [x] 5.1 `cache.put_recipe(recipe_id, group_id=None)`, адаптировать `/open`-поток
- [x] 5.2 `rotation` — ключ `(user_id, category_id)`

## 6. UI — клавиатуры и меню
**Файлы:** `handlers/keyboards.py`, `handlers/menu.py`, `handlers/buttons.py`

- [x] 6.1 `build_menu_keyboard(group_id)` (динамическая reply) + кнопка «➕ Категория»
- [x] 6.2 `category_select_keyboard(group_id, current_category_id, rk)` — для «Перенести»
- [x] 6.3 `handlers/menu.py`: динамический матч кнопки → category_id, `category_id` в колбэках, категория в сообщении печатается хендлером
- [x] 6.4 `handlers/buttons.py`: колбэки `del/rcat/mov` через `category_id`; `handle_move` вызывает `move_recipe_in_group`
- [x] 6.5 Убрать хардкод `MENU_KEYBOARD` и `F.text.in_(["🌅 Завтрак", ...])`

## 7. UI — управление категориями
**Файлы:** `handlers/categories.py` (новый), `bot.py`

- [x] 7.1 Подменю «🗂 Категории»: список + кнопки add/rename/delete
- [x] 7.2 FSM `CategoryStates` (waiting_for_name, waiting_for_rename, confirm_delete)
- [x] 7.3 Хендлеры add/rename/delete с валидацией (1–50 симв., уникальность, лимит 30, запрет удаления default)
- [x] 7.4 Регистрация роутера в `bot.py`

## 8. Модели и константы
**Файлы:** `models/recipe.py`, `constants.py`, `models/category.py` (новый)

- [x] 8.1 `models/recipe.py`: `format_message` без строки категории; `to_markdown` без обязательного `category:`; `from_markdown` толерантен к отсутствию category
- [x] 8.2 `models/category.py` — dataclass `Category(category_id, group_id, name, position, is_default)`
- [x] 8.3 `constants.py`: `DEFAULT_CATEGORIES` (seed: name, position, is_default), `MAX_CATEGORIES_PER_GROUP`; удалить `VALID_CATEGORIES`, `MENU_BUTTON_TO_CATEGORY`, `CATEGORY_TO_CODE`, `CODE_TO_CATEGORY`, `category_to_code`, `code_to_category`

## 9. Dashboard
**Файлы:** `dashboard/pages/3_🍳_Рецепты.py`, `dashboard/pages/1_📊_Обзор.py`, `dashboard/pages/4_🔍_Поиск.py`

- [x] 9.1 `3_🍳_Рецепты.py`: запросы через `recipe_id`, категория как пер-групп поле (JOIN `group_recipes` + `group_categories`)
- [x] 9.2 Проверить ссылки на `category` в обзорном и поисковом страницах — адаптировать

## 10. Тесты и приёмка
**Файлы:** `tests/unit/test_db_schema.py`, `tests/unit/test_parser.py`, `tests/unit/test_buttons.py`, `tests/unit/test_menu.py`, `tests/unit/test_models.py`

- [x] 10.1 `test_db_schema.py`: тест миграции старая→новая схема, дедуп slug, сидирование категорий, idempotent
- [x] 10.2 `test_parser.py`: динамические категории + fallback
- [x] 10.3 `test_models.py`, `test_menu.py`, `test_buttons.py` — адаптировать под новые сигнатуры
- [x] 10.4 `pytest` зелёный
- [ ] 10.5 Ручной смок на копии реальной БД (бэкап → миграция → сверка счетчиков)
- [x] 10.6 Добавить инструкцию по бэкапу `bot.db` в README/DEPLOYMENT

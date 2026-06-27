# Design: Пользовательские категории рецептов

## Контекст и решения explore-режима

Категории **scoped по группе** (личная группа `pers_{user_id}` = персональный набор). LLM выбирает категорию из списка активной группы, при неуверенности — `is_default`. Новый пользователь получает копию 3 дефолтных. На рецепт в рамках группы — одна категория. Дубль-рилс в новой группе уходит в дефолтную категорию. CRUD MVP: добавить / переименовать / удалить.

## Целевая схема

```sql
group_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    TEXT    NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    is_default  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (group_id, name)
);

recipes (
    recipe_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    slug             TEXT    NOT NULL,
    title            TEXT    NOT NULL DEFAULT '',
    content_md       TEXT    NOT NULL DEFAULT '',
    source           TEXT    NOT NULL DEFAULT '',
    full_text_lemmas TEXT    NOT NULL DEFAULT '',
    created          TEXT    NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX idx_recipes_slug ON recipes(slug);

recipe_ingredients (
    recipe_id         INTEGER NOT NULL REFERENCES recipes(recipe_id) ON DELETE CASCADE,
    ingredient        TEXT    NOT NULL,
    ingredient_lemmas TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (recipe_id, ingredient)
);

reel_index (
    reel_id   TEXT    PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipes(recipe_id) ON DELETE CASCADE
);

group_recipes (
    group_id          TEXT    NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    recipe_id         INTEGER NOT NULL REFERENCES recipes(recipe_id) ON DELETE CASCADE,
    category_id       INTEGER NOT NULL REFERENCES group_categories(category_id),
    added_at          TEXT,
    added_by_user_id  INTEGER,
    PRIMARY KEY (group_id, recipe_id)
);
```

## Отображение требований на схему

| Требование | Механизм |
|---|---|
| Свои категории у каждого | `group_categories` per group; `pers_{user_id}` — личный набор |
| Определение среди категорий юзера | LLM-промпт получает имена категорий активной группы |
| Один рецепт в разных категориях у разных юзеров | `reel_id → recipe_id` (1:1); разные группы вешают разные `category_id` |
| Перемещение не влияет на других | `UPDATE group_recipes SET category_id=? WHERE group_id=? AND recipe_id=?` — 1 строка |

## Поток добавления рецепта (`recipe_pipeline.process_video`)

1. `find_recipe_by_source(url)` → `recipe_id | None`.
2. **recipe_id уже есть**:
   - Рецепт уже в активной группе → показать существующий (с его `category_id` в этой группе).
   - Иначе → `add_recipe_to_group(group_id, recipe_id, default_category_id, user_id)`; показать с кнопкой «Перенести».
3. **recipe_id нет**: стандартный пайплайн (download/transcribe/parse). `generate_recipe(..., categories, default)`; сохранить рецепт **без** категории (`save_recipe` без category); зарезолвить ответ LLM в `category_id` (мимо → default); `register_source(url, recipe_id)`; `add_recipe_to_group`.

## LLM-категоризация (`recipe_parser`)

- `prompts/system.txt` превращается в шаблон с плейсхолдерами `{categories}` и `{default}`.
- `generate_recipe(transcription, caption, source, categories: list[str], default: str)` собирает промпт под активную группу.
- `_parse_recipe_response` матчит строку «Категория:» против переданного `categories` (регистронезависимо, contains); не сматчилось → `default`.
- Поле `Recipe.category` сохраняется как **транзиентный suggestion** — только для выбора `category_id` при добавлении в группу; в `content_md` больше не записывается как источник истины.

## Категория в отображении рецепта

`Recipe.format_message` больше не печатает `📂 Категория: ...`. Хендлер, знающий контекст активной группы, достаёт имя категории из `group_recipes.category_id → group_categories.name` и дописывает строку сам. `cache.put_recipe` хранит `recipe_id` (+ при необходимости `group_id`).

## Callback-коды

`category_to_code` / `code_to_category` (односимвольные `z/o/d`) упраздняются. В `callback_data` используется сам `category_id` (целое): `del:{cid}:{rk}`, `rcat:{cid}:{rk}`, `mov:{new_cid}:{old_cid}:{rk}`. Лимит 64 байт не критичен для integer-кодов.

## Меню (reply-клавиатура)

`MENU_KEYBOARD` (хардкод 3 кнопки) → `build_menu_keyboard(group_id)`: кнопки из категорий активной группы + «🔍 Поиск», «👥 Группы», «➕ Категория». `handle_menu_category` матчит текст кнопки на категорию группы через мапу `button_text → category_id` (в рамках сессии активная группа одна, коллизий нет).

## CRUD категорий (add / rename / delete)

- **Add**: «➕ Категория» → FSM ввод имени → `create_category(group_id, name)`. Валидация: 1–50 символов, уникальность в группе, лимит `MAX_CATEGORIES_PER_GROUP` (30).
- **Rename**: из подменю «🗂 Категории» → FSM → `rename_category(group_id, category_id, new_name)`.
- **Delete**: `delete_category(group_id, category_id)`:
  - Запрет, если `is_default=1` (защита основы; в группе всегда минимум одна default).
  - Рецепты удаляемой категории → переносятся в default-категорию этой же группы одним `UPDATE`.
- Порядок (reorder) — вне MVP; `position` хранится про запас (по умолчанию = порядок создания).

## Rotation

Ключ `services/rotation.py` меняется с `(user_id, category)` (текст) на `(user_id, category_id)`. Хранилище in-memory, данных для миграции нет — меняются только сигнатуры и точки вызова в `handlers/menu.py`.

## Миграция данных (table-rebuild в `_migrate`, одна транзакция)

1. **Детект** старой схемы: в `recipes` нет колонки `recipe_id` (через `PRAGMA table_info`).
2. Создать новые таблицы (с времoral суффиксом `_new`, либо сразу финальные имена при пересоздании).
3. **recipes**: для каждого уникального `slug` (из старой `recipes`) — одна строка. При коллизии `(catA, slug)` vs `(catB, slug)`:
   - одинаковый `content_md` → слить в один `recipe_id`;
   - разный `content_md` → второму дописать суффикс `-2/-3` в slug (переиспользуется логика `save_recipe_as_new`).
4. **recipe_ingredients**: перенос по маппингу старый `(category, slug)` → новый `recipe_id`; дедуп ingredient по `recipe_id`.
5. **reel_index**: `reel_id → recipe_id` (если старая пара слилась — взять результирующий `recipe_id`).
6. **group_categories**: для каждой группы сидировать 3 дефолта + уникальные текстовые значения `category` из её `group_recipes`, не совпадающие с дефолтами.
7. **group_recipes**: `(group_id, recipe_id, category_id)` с маппингом `(group_id, category_text) → category_id`.
8. `DROP` старых таблиц, `RENAME` новых, пересоздать индекс `idx_recipes_slug`.
9. Транзакция целиком; при ошибке — откат, БД не тронута.

**Бэкап `data/bot.db` обязателен перед первым запуском с миграцией.**

## Риски и митигации

| Риск | Митигация |
|---|---|
| Table-rebuild — точка отказа | Одна транзакция; тесты миграции на синтетической старой схеме в `test_db_schema.py`; инструкция по бэкапу/откату в README |
| Слияние одинаковых slug с разным контентом | Суффиксация (как `save_recipe_as_new`); случай редкий |
| Старые закэшированные колбэки невалидны после миграции | Кэш TTL=1ч и in-memory — очищается при рестарте |
| `Recipe.category` в YAML существующих рецептов | `from_markdown` уже пропускает неизвестные поля; новые рецепты не пишут `category:` как истину |
| Дашборд ломается | Запросы переписать под `recipe_id` в рамках того же change |

## Решения

### Почему категория ушла из PK рецепта
Пока `category` в PK, требование «один рецепт в разных категориях у разных пользователей» требует дублирования контента рецепта под каждым вариантом категории и ломает дедупликацию по рилсу. Суррогатный `recipe_id` + `category_id` в членстве решает обе проблемы.

### Почему `slug` остался UNIQUE
Сохраняет текущую семантику дедупа по названию (`check_duplicate`, `save_recipe_as_new`). Альтернатива (не-уникальный slug) потребовала бы повсеместной замены идентификации на `recipe_id` в UI/`/open` — избыточно при текущем масштабе.

### Почему default неудаляем
Гарантирует, что в группе всегда есть «амортизирующая» категория для удаления других категорий и для дубль-рилсов. Удаление default разрушило бы инвариант.

### Почему reorder не в MVP
`position` заложен в схему, но UI reorder добавляет FSM/кнопки без критической ценности — отложен в отдельный change.

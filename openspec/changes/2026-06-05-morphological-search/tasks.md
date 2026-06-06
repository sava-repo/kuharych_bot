# Tasks: morphological-search

## Задачи

### 1. Зависимость и модуль лемматизации
**Файлы:** `requirements.txt`, `services/lemmatizer.py`

- [x] Добавить `pymorphy3>=2.0` в `requirements.txt` (для Py3.11+, fallback на pymorphy2 для старых версий)
- [x] Создать `services/lemmatizer.py`:
  - [x] Lazy-singleton `MorphAnalyzer` (через функцию `_get_morph()`)
  - [x] Константа `_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)`
  - [x] Константа `_STOP_POS = {"PREP","CONJ","PRCL","INTJ","NPRO"}`
  - [x] Функция `normalize_word(word: str) -> str` — возвращает нормальную форму или `""` для чисел/стоп-слов
  - [x] Функция `lemmatize_text(text: str) -> list[str]` — токенизация, фильтрация, лемматизация, дедупликация с сохранением порядка
  - [x] `@lru_cache(maxsize=4096)` на `_normalize_token()` для повторно используемых слов

### 2. Миграция схемы и backfill
**Файл:** `services/database.py`

- [x] В `_init_db()` в `CREATE TABLE recipe_ingredients` добавить колонку `ingredient_lemmas TEXT NOT NULL DEFAULT ''`
- [x] Добавить метод `_migrate_recipe_lemmas_column()` (через pragma `table_info` + ALTER TABLE)
- [x] Добавить метод `_migrate_ingredient_lemmas_backfill()`:
  - [x] SELECT строк с пустым `ingredient_lemmas` (через `connect_raw()` — без рекурсии в `_init_db`)
  - [x] Вычислить леммы через `services.lemmatizer.lemmatize_text()`
  - [x] UPDATE каждой строки
- [x] Вызывать обе миграции в `_init_db()` после `_migrate_from_json()`

### 3. Индексация ингредиентов
**Файл:** `services/group_manager.py`

- [x] Импортировать `from services import lemmatizer`
- [x] В `index_recipe_ingredients()`:
  - [x] Для каждой строки `ingredient` вычислять `lemmas = lemmatizer.lemmatize_text(ing)`
  - [x] Сохранять `ingredient_lemmas = " ".join(lemmas)` в новую колонку
- [x] Обновить `INSERT` на `INSERT OR REPLACE INTO recipe_ingredients (category, slug, ingredient, ingredient_lemmas) VALUES (?, ?, ?, ?)`

### 4. Поиск
**Файл:** `services/group_manager.py`

- [x] В `search_recipes_by_ingredient()`:
  - [x] Ранний возврат `[]` для пустого/whitespace запроса
  - [x] Лемматизировать запрос: `query_lemmas = lemmatizer.lemmatize_text(query)`
  - [x] Если `query_lemmas` пуст — вернуть `[]` (защита от запросов из цифр/стоп-слов)
  - [x] Динамически построить SQL с одним или несколькими `AND ri.ingredient_lemmas LIKE ?`
  - [x] Параметры — `%lemma%` для каждой леммы + `group_id` + `category`

### 5. Спецификация (delta)
**Файл:** `openspec/changes/2026-06-05-morphological-search/specs/search-by-ingredient/spec.md`

- [x] Создать дельту: переопределить раздел «Условия» — поиск ведётся по леммам через pymorphy, `LIKE` применяется к нормализованной строке
- [x] Переопределить SQL — указать `ingredient_lemmas LIKE '%lemma%'`
- [x] Указать поведение multi-lemma запросов (AND по всем леммам)

### 6. Тесты
**Файлы:** `tests/unit/test_lemmatizer.py`, `tests/unit/test_search_morph.py`

- [x] Unit-тесты на `lemmatizer.py`:
  - [x] `normalize_word("яйца") == "яйцо"`
  - [x] `normalize_word("индейка") == "индейка"`
  - [x] `normalize_word("индейку") == "индейка"` (родительный падеж)
  - [x] `normalize_word("молока") == "молоко"`
  - [x] `"яйцо" in lemmatize_text("10 яиц")`
  - [x] `"10" not in lemmatize_text("10 яиц")`
  - [x] `"индейка" in lemmatize_text("филе индейки")`
  - [x] `set(["куриный","грудка"]).issubset(lemmatize_text("куриная грудка"))`
  - [x] `lemmatize_text("") == []`
  - [x] Дедупликация с сохранением порядка
  - [x] Фильтрация предлогов («молоко с солью» → нет «с»)
- [x] Unit-тест на поиск с морфологией (test_search_morph.py, через monkeypatch DATABASE_PATH):
  - [x] Поиск «яйца» → находит рецепт с «10 яиц»
  - [x] Поиск «яйцо» → находит рецепт с «10 яиц»
  - [x] Поиск «индейка» → находит рецепт с «филе индейки»
  - [x] Поиск «куриная грудка» → находит рецепт с «куриная грудка» (AND по двум леммам)
  - [x] Поиск «курица» → НЕ находит «куриная грудка» (нет ложных срабатываний без синонимов)
  - [x] Запрос из цифр («10») → `[]`
  - [x] Несовпадающая категория → `[]`
  - [x] Пустой запрос → `[]`

### 7. Прогон тестов
- [x] `pytest tests/unit/test_lemmatizer.py tests/unit/test_search_morph.py -v` → **25 passed in 0.25s**
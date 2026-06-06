# Design: Морфологический поиск по ингредиентам

## Архитектура

### Обзор

Поиск по ингредиентам переводится с «голого» `LIKE` по исходной строке на `LIKE` по лемматизированному представлению. Лемматизация выполняется на стороне приложения через `pymorphy2` — морфологический анализатор русского языка (чистый Python + упакованные словари).

Поток данных:

```
Рецепт «10 яиц»
  └── index_recipe_ingredients()
        ├── ingredient = "10 яиц"
        └── ingredient_lemmas = "десять яйцо"          ← lemmatize_text("10 яиц")

Поиск «яйца»
  └── search_recipes_by_ingredient()
        └── запрос лемматизируется: "яйцо"
        └── SQL: WHERE ingredient_lemmas LIKE '%яйцо%'
              → найдено
```

### Уровень приложения: `services/lemmatizer.py`

Новый модуль-обёртка над `pymorphy2.MorphAnalyzer`. Дизайн-решения:

- **Singleton на уровне модуля**. `MorphAnalyzer` при инициализации загружает словарь (~10 МБ). Создание на каждый запрос недопустимо по производительности. Создаётся лениво при первом обращении.
- **Токенизация** — простая регекс-нарезка по границам слов (`\w+` с поддержкой кириллицы через `re.UNICODE`).
- **Фильтры**:
  - удаляются токены, состоящие только из цифр (количества: «10», «300г»);
  - удаляются местоимения, предлоги, союзы, частицы (`POS in {'PREP','CONJ','PRCL','INTJ','NPRO'}`);
  - остаются существительные, прилагательные, глаголы, наречия и прочие знаменательные слова.
- **Лемматизация** — `morph.normal_forms(word)[0]` (первая нормальная форма; для неоднозначных слов берётся наиболее вероятная).
- **Публичные функции**:
  - `normalize_word(word: str) -> str` — для однословного запроса пользователя (если ввёл «яйца», вернёт «яйцо»; если ввёл «10», вернёт `""`).
  - `lemmatize_text(text: str) -> list[str]` — для строк ингредиента, возвращает список уникальных лемм в порядке появления.

### Уровень данных: схема SQLite

Текущая таблица:

```sql
CREATE TABLE recipe_ingredients (
    category TEXT NOT NULL,
    slug TEXT NOT NULL,
    ingredient TEXT NOT NULL,
    PRIMARY KEY (category, slug, ingredient)
);
```

После миграции:

```sql
ALTER TABLE recipe_ingredients
    ADD COLUMN ingredient_lemmas TEXT NOT NULL DEFAULT '';
```

Колонка `ingredient_lemmas` содержит пробел-разделённые леммы: `"десять яйцо"`, `"филе индейка"`, `"куриный грудка"`.

**Почему отдельная колонка, а не замена `ingredient`:**
- обратная совместимость (старый код/дашборд могут читать `ingredient`);
- проще отладка (видно и исходную форму, и нормальную);
- для последующего переиндекса/аудита.

**Почему не отдельная таблица «одна лемма = одна строка»:**
- текущий масштаб (десятки-сотни рецептов) не требует нормализации до 1NF;
- `LIKE` по пробел-разделённой строке достаточно для поиска отдельной леммы как подстроки (леммы не содержат пробелов);
- меньше JOIN'ов и проще код.

### Уровень данных: запрос поиска

Было:

```sql
SELECT DISTINCT ri.slug
FROM recipe_ingredients ri
INNER JOIN group_recipes gr
    ON gr.category = ri.category AND gr.slug = ri.slug
WHERE ri.ingredient LIKE ?
  AND gr.group_id = ?
  AND ri.category = ?
```

Стало:

```sql
SELECT DISTINCT ri.slug
FROM recipe_ingredients ri
INNER JOIN group_recipes gr
    ON gr.category = ri.category AND gr.slug = ri.slug
WHERE ri.ingredient_lemmas LIKE ?
  AND gr.group_id = ?
  AND ri.category = ?
```

Если запрос пользователя содержит несколько слов (например, «куриная грудка»), функция поиска:
1. лемматизирует каждое слово → `["куриный","грудка"]`;
2. строит запрос с `AND` по всем леммам:

```sql
WHERE ri.ingredient_lemmas LIKE '%куриный%'
  AND ri.ingredient_lemmas LIKE '%грудка%'
```

Это даёт «точный» поиск по фразе. Для однословного запроса — одно условие `LIKE`.

### Миграция существующих данных

Проблема: в таблице уже могут быть строки с `ingredient_lemmas = ''` (созданные до миграции).

Решение — процедура `_migrate_ingredient_lemmas()` в `services/database.py`, запускаемая в `_init_db()` после `_migrate_from_json()`:

```python
def _migrate_ingredient_lemmas(self) -> None:
    """Заполняет ingredient_lemmas для строк без них."""
    with self.connect() as conn:
        rows = conn.execute(
            "SELECT category, slug, ingredient FROM recipe_ingredients "
            "WHERE ingredient_lemmas = '' OR ingredient_lemmas IS NULL"
        ).fetchall()
        for row in rows:
            lemmas = lemmatizer.lemmatize_text(row["ingredient"])
            if lemmas:
                conn.execute(
                    "UPDATE recipe_ingredients SET ingredient_lemmas = ? "
                    "WHERE category = ? AND slug = ? AND ingredient = ?",
                    (" ".join(lemmas), row["category"], row["slug"], row["ingredient"]),
                )
```

Идемпотентно: после заполнения условие `WHERE ingredient_lemmas = ''` не возвращает строк.

Альтернатива (один `UPDATE` с Python-вычислением в цикле вне SQL) менее эффективна и читаема.

### Производительность

- `pymorphy2.MorphAnalyzer()` — инициализация ~100–200 мс один раз за жизненный цикл процесса.
- Один вызов `lemmatize_text("10 яиц")` — ~1 мс на современном железе.
- Миграция 1000 строк — ~1 секунда, одноразово при первом запуске после деплоя.
- Поиск — без регрессии: один SQL-запрос, как и раньше.

### Интеграция с существующим кодом

| Точка | Файл | Изменение |
|-------|------|-----------|
| Сохранение нового рецепта | `services/recipe_pipeline.py` | без изменений (вызов `index_recipe_ingredients` уже есть) |
| Перезапись рецепта | `handlers/buttons.py:handle_overwrite` | без изменений (вызов `index_recipe_ingredients` уже есть) |
| Сохранить как новый | `handlers/buttons.py:handle_save_new` | без изменений (вызов `index_recipe_ingredients` уже есть) |
| Индексация | `services/group_manager.py:index_recipe_ingredients` | вычислять `ingredient_lemmas` и сохранять в новую колонку |
| Удаление рецепта | `handlers/buttons.py:handle_delete` | без изменений (удаляется вся строка) |
| Поиск | `services/group_manager.py:search_recipes_by_ingredient` | лемматизировать запрос, искать по `ingredient_lemmas` |
| Схема БД | `services/database.py:_init_db` | `ALTER TABLE` + backfill |

## Решения

### Почему pymorphy2, а не стеммер (Snowball)

- pymorphy2 использует словарь + предиктор: качество выше, корректно обрабатывает неправильные формы, аббревиатуры, предикт для неизвестных слов.
- Snowball работает по правилам, ошибается на сложных случаях («люди» → ?).
- Лицензия pymorphy2 (MIT) совместима с проектом.

### Почему LIKE по строке лемм, а не 1NF-таблица

- Меньше JOIN'ов и проще запрос (важно: SQLite без FTS).
- LIKE по подстроке с пробелами-разделителями надёжен, т.к. леммы не содержат пробелов.
- При росте масштаба можно мигрировать на `recipe_ingredient_lemmas(category, slug, lemma)` без изменения публичного API.

### Почему нет FTS5

- Текущий масштаб — десятки-сотни рецептов. FTS5 усложняет схему, миграции и операции записи (триггеры для синхронизации).
- LIKE по лемматизированной строке достаточно для морфологического поиска.
- FTS5 не даёт морфологии «из коробки» (нужен внешний токенизатор или Russiansnowball-wrapper).

### Почему лемматизация в Python, а не SQL-функцией

- SQLite не имеет встроенной поддержки русского; пользовательские функции требуют расширений.
- Python-сторона проще тестируется, отлаживается и обновляется.

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| pymorphy2 недоступен на Amvera | Проверяется при установке; пакет — pure Python + скомпилированные словари, ставится через pip без системных зависимостей |
| Медленный первый запрос после старта | Singleton `MorphAnalyzer` — инициализация один раз |
| Ошибка лемматизации для специфичного слова («филе» может быть несклоняемым) | pymorphy2 корректно возвращает `филе` как несклоняемое; тесты покрывают такие кейсы |
| Большой объём миграции | На текущих данных — миллисекунды; при росте можно делать backfill пакетами |

## Тестирование

- Unit-тесты `services/lemmatizer.py`:
  - `normalize_word("яйца") == "яйцо"`
  - `normalize_word("индейка") == "индейка"`
  - `lemmatize_text("10 яиц")` содержит `"яйцо"` (без `"10"`)
  - `lemmatize_text("филе индейки")` содержит `"индейка"`
  - `lemmatize_text("куриная грудка")` содержит `"куриный"` и `"грудка"`
  - `lemmatize_text("")` возвращает `[]`
- Unit-тест `search_recipes_by_ingredient`:
  - индексируется рецеп с ингредиентом «10 яиц»;
  - поиск «яйца» находит рецепт;
  - поиск «яйцо» находит рецепт.
- Интеграционный сценарий «филе индейки»:
  - поиск «индейка» находит рецепт.
# Tasks: search-by-ingredient

## Задачи

### 1. Таблица `recipe_ingredients` + функции в `group_manager.py`
**Файл:** `services/group_manager.py`

- [ ] Добавить `CREATE TABLE IF NOT EXISTS recipe_ingredients` в `_init_db()`
- [ ] Добавить функцию `index_recipe_ingredients(category, slug, ingredients: list[str])` — INSERT OR REPLACE для каждого ингредиента
- [ ] Добавить функцию `remove_recipe_ingredients(category, slug)` — DELETE всех ингредиентов рецепта
- [ ] Добавить функцию `search_recipes_by_ingredient(group_id, query, category) -> list[str]` — JOIN с group_recipes, LIKE поиск
- [ ] Обновить `move_recipe_category()` — добавить UPDATE recipe_ingredients SET category

### 2. Кнопка «🔍 Поиск» и FSM в `menu.py`
**Файл:** `handlers/menu.py`

- [ ] Импортировать `State, StatesGroup` из aiogram
- [ ] Создать класс `SearchState(StatesGroup)` с `waiting_for_ingredient`
- [ ] Добавить кнопку «🔍 Поиск» в `MENU_KEYBOARD`
- [ ] Добавить обработчик `handle_search_start()` — реагирует на «🔍 Поиск», устанавливает FSM
- [ ] Добавить обработчик `handle_search_ingredient()` — реагирует в FSM-состоянии, кэширует данные, показывает inline-категории
- [ ] Добавить callback `handle_search_category()` — реагирует на `srch:{cc}:{ck}`, выполняет поиск, показывает рецепт
- [ ] Добавить callback `handle_search_random()` — реагирует на `srnd:{cc}:{ck}`, показывает другой результат

### 3. Индексация при сохранении в `link.py`
**Файл:** `handlers/link.py`

- [ ] После `gm.add_recipe_to_group()` — добавить `gm.index_recipe_ingredients(category, slug, recipe.ingredients)`

### 4. Индексация в `buttons.py`
**Файл:** `handlers/buttons.py`

- [ ] `handle_overwrite` — после перезаписи: `remove_recipe_ingredients` + `index_recipe_ingredients`
- [ ] `handle_save_new` — после сохранения копии: `index_recipe_ingredients`
- [ ] `handle_move` — обновление category в recipe_ingredients уже в `move_recipe_category()`
- [ ] `handle_delete` — при полном удалении из GitHub: `remove_recipe_ingredients`
# Tasks: recipe-portion-scaling

## 1. Парсер-сервис
**Файлы:** `services/ingredient_scaler.py`

- [x] 1.1 `scale_ingredient(ingredient, factor: Fraction) -> str`: regex ведущего числа (смешанная дробь / диапазон / дробь / десятичная / целое) в порядке longest-match; масштабирование через `Fraction`; сборка строки обратно (число заменяется, остаток — единица/продукт — сохраняется). Без числа → строка как есть.
- [x] 1.2 Форматирование Fraction: целый → `str(int)`; дробный → округление до 2 знаков, без хвостовых нулей, русская запятая (`0,75`). Диапазон: оба конца → целые (half-up).
- [x] 1.3 `scale_ingredients(ingredients, factor) -> list[str]` — применение по списку.

## 2. Модель Recipe
**Файлы:** `models/recipe.py`

- [x] 2.1 `format_message(category_name=None, *, portions_override=None)`: при `portions_override` и `portions_override != self.portions` и `self.portions > 0` — `factor = Fraction(portions_override, self.portions)`, ингредиенты через `scale_ingredients`. Иначе — исходные.
- [x] 2.2 КБЖУ-строка (`_nutrition_line`) остаётся без изменений (на `self.portions`).

## 3. Клавиатура
**Файлы:** `handlers/keyboards.py`

- [x] 3.1 Расширить `recipe_keyboard` опциональными `base_portions: int = 0`, `current_portions: int | None = None`: при `base_portions > 0` добавлять ряд `[➖][N порций][➕]` с `callback_data=f"psc:{rk}:{target}"`; скрытие `➖` при `current==1`, `➕` при `current==20`.
- [x] 3.2 При `current_portions is None` — `current = base_portions` (первичный показ).
- [x] 3.3 Сохранить существующие кнопки (🗑/📂/▶️) и раскладку `adjust` (ряд порций отдельный).

## 4. Хендлеры
**Файлы:** `handlers/buttons.py`, `handlers/menu.py`

- [x] 4.1 `handle_portions_change` (`F.data.startswith("psc:")`): парсинг `psc:{rk}:{target}`, clamp `target` в 1..20; `cache.get(rk)` → `recipe_id/group_id`; загрузка рецепта; `format_message(portions_override=target)`; клавиатура с `current_portions=target`. При отсутствии `rk`/рецепта — «данные устарели».
- [x] 4.2 `menu.py` `_random_recipe_markup`: передать `base_portions=result['recipe'].portions` в `recipe_keyboard`.
- [x] 4.3 `menu.py` `handle_open_recipe`: то же — `base_portions=recipe.portions`.
- [x] 4.4 `buttons.py` `_restore_recipe_view`: `base_portions=recipe.portions` (возврат к базовому виду, `current_portions=None`). `handle_move` показывает тост подтверждения — ряд порций там не нужен (не является отображением рецепта).
- [x] 4.5 `link.py` сохранение дубликата — без изменений (без кнопок порций).

## 5. Тесты и приёмка
**Файлы:** `tests/unit/test_ingredient_scaler.py`, `test_models.py`, `test_buttons.py`

- [x] 5.1 `test_ingredient_scaler`: целое (`400 ×3/2 → 600`), десятичная (`1,5 ×3/2 → 2,25`), дробь (`1/2 ×3/2 → 3/4 → "0,75"`), смешанная (`1 1/2 ×2 → 3`), диапазон (`3-4 ×3/2 → "5-6"`), без числа (`по вкусу` — как есть), единицы сохраняются (`400 г говядины → 600 г говядины`).
- [x] 5.2 `test_models`: `format_message(portions_override=6)` масштабирует ингредиенты; без override — исходные; `portions_override == portions` — без изменений; КБЖУ-строка неизменна при override.
- [x] 5.3 `test_buttons`: `psc:{rk}:6` рендерит масштабированные ингредиенты, клавиатура с `current=6`; clamp target>20 → 20; протухший rk → «устарели».
- [x] 5.4 `pytest` зелёный (предсуществующие 4 падения `TestRecipeSlug` не связаны с изменением — подтверждено через `git stash`).
- [ ] 5.5 Ручной смок: случайный рецепт → `+/−` → ингредиенты пересчитываются, шаги и КБЖУ на месте; рецепт с `portions==0` → кнопок нет.

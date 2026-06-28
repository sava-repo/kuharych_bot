# Tasks: recipe-nutrition

## 1. Промпты
**Файлы:** `prompts/system.txt`, `prompts/nutrition.txt`

- [x] 1.1 Дополнить `prompts/system.txt`: в формат ответа после `Категория:` добавить блок `Порции/Калории/Белки/Жиры/Углеводы` (тотальные, целые) с краткой инструкцией «оценить ориентировочно по составу продуктов»
- [x] 1.2 Создать `prompts/nutrition.txt` — только-КБЖУ промпт: на вход title + ingredients + steps, на выходе только `Порции/Калории/Белки/Жиры/Углеводы`, без переизвлечения рецепта
- [x] 1.3 Проверить, что шаблоны `{categories}`/`{default}` в `system.txt` сохранены

## 2. Модель Recipe
**Файлы:** `models/recipe.py`

- [x] 2.1 Добавить 5 полей в dataclass `Recipe`: `portions: int = 0`, `calories: int = 0`, `protein: int = 0`, `fat: int = 0`, `carbs: int = 0` (тотальные значения)
- [x] 2.2 `format_message`: под названием, при `calories > 0` и `portions > 0`, выводить `≈{cal//portions} ккал · Б {p//portions} / Ж {f//portions} / У {c//portions}` со скобками `(1 порция из {portions})` / `(на 1 порцию)` при `portions==1`
- [x] 2.3 `to_markdown`: дописать в YAML frontmatter (после `tags`) строки `portions/calories/protein/fat/carbs`
- [x] 2.4 `from_markdown`: парсить `portions/calories/protein/fat/carbs` из frontmatter; при отсутствии — значения по умолчанию 0; дополнить список пропускаемых ключей, чтобы старые frontmatter читались без ошибок

## 3. Парсер
**Файлы:** `services/recipe_parser.py`

- [x] 3.1 В `_parse_recipe_response` добавить извлечение 5 значений из строк `Порции:`/`Калории:`/`Белки:`/`Жиры:`/`Углеводы:` (часть после `:`, `int(...)` с защитой от `ValueError` и пустоты → поле `0`)
- [x] 3.2 Прокинуть значения в конструктор `Recipe(...)` вместе с category/tags
- [x] 3.3 Убедиться, что отсутствие блока КБЖУ в ответе не валит парсинг (поля `0`)

## 4. Бэкфилл
**Файлы:** `services/nutrition.py`, `services/nutrition_backfill.py`

- [x] 4.1 Создать `services/nutrition.py`: dataclass `NutritionEstimate(portions, calories, protein, fat, carbs)`
- [x] 4.2 `estimate_nutrition(recipe: Recipe) -> NutritionEstimate` — LLM-вызов с `prompts/nutrition.txt` (title + ingredients + steps → 5 чисел); парсинг ответа с защитой от не-чисел (→ 0)
- [x] 4.3 `backfill_all(*, dry_run: bool = False, limit: int | None = None) -> BackfillReport` — итерация `recipes` через `gm`/`db`: для `calories == 0` вызывать `estimate_nutrition`, пересобрать `content_md` (`to_markdown` с подставленными total), `UPDATE recipes SET content_md=? WHERE recipe_id=?`; не трогать `recipe_ingredients`/`reel_index`/`group_recipes`; логинг прогресса
- [x] 4.4 Создать `services/nutrition_backfill.py` с `if __name__ == "__main__":` — парсинг `argv` (`--dry-run`, `--limit N`), `asyncio.run(backfill_all(...))`, печать отчёта (обработано/пропущено/ошибок)
- [x] 4.5 `BackfillReport`: счётчики `processed`, `skipped`, `failed`, список `failed_ids`

## 5. Тесты и приёмка
**Файлы:** `tests/unit/test_models.py`, `tests/unit/test_parser.py`, `tests/unit/test_nutrition.py`

- [x] 5.1 `test_models.py`: `format_message` выводит строку КБЖУ при `calories>0` + корректное деление; не выводит при `calories==0`/`portions==0`; `portions==1` → `(на 1 порцию)`
- [x] 5.2 `test_models.py`: round-trip `to_markdown` → `from_markdown` сохраняет КБЖУ; `from_markdown` старого frontmatter (без блока КБЖУ) даёт поля 0 без ошибок
- [x] 5.3 `test_parser.py`: `_parse_recipe_response` извлекает КБЖУ из ответа; толерантность к не-числам и отсутствию строк (поля 0)
- [x] 5.4 `test_nutrition.py`: `estimate_nutrition` парсит 5 чисел из мок-ответа LLM; `backfill_all` (с замоканным LLM и временной БД) обновляет `content_md` только для рецептов без КБЖУ, пропускает уже с КБЖУ, `dry_run` не пишет
- [x] 5.5 `pytest` зелёный
- [ ] 5.6 Ручной смок: прислать тестовый рилс → проверить наличие строки КБЖУ; запустить `python -m services.nutrition_backfill --dry-run --limit 3` на копии БД → сверить отчёт

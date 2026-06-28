# Design: Пересчёт ингредиентов по числу порций

## Контекст

Базовое число порций `recipe.portions` уже проставляет LLM (change `recipe-nutrition`). Этот change использует его как знаменатель коэффициента масштабирования `factor = target_portions / recipe.portions`. Ингредиенты — свободный текст (`list[str]`), значит число разбирается regex-ом на рендере. Результат не пишется в БД — только в сообщение.

## Парсер `services/ingredient_scaler.py`

Грамматика ведущего числа (якорь в начале строки, пробелы слева допустимы), проверяются по порядку — длинное совпадение первым:

| Паттерн | Пример | В `Fraction` |
|---|---|---|
| `(\d+)\s+(\d+)/(\d+)` смешанная | `1 1/2` | `Fraction(1) + Fraction(1,2)` |
| `(\d+)\s*[-–—]\s*(\d+)` диапазон | `3-4` | пара `(Fraction(3), Fraction(4))` |
| `(\d+)/(\d+)` дробь | `1/2` | `Fraction(1,2)` |
| `(\d+[.,]\d+)` десятичная | `1,5` / `1.5` | `Fraction(Decimal("1.5"))` |
| `(\d+)` целое | `400` | `Fraction(400)` |
| нет числа | `по вкусу соль` | без изменений |

Арифметика на `fractions.Fraction` — точно, без float-грязи (400 × 3/2 = 600 ровно; 1/2 × 3/2 = 3/4).

### API

```python
def scale_ingredients(ingredients: list[str], factor: Fraction) -> list[str]:
    """Масштабирует ведущее число в каждой строке; без числа — как есть."""

def scale_ingredient(ingredient: str, factor: Fraction) -> str:
    """Масштабирует одну строку. factor > 0."""
```

### Форматирование результата

- Целый результат (`denominator == 1`): `str(numerator)` → `600`, `3`.
- Дробный: float, округление до 2 знаков, без хвостовых нулей, русская запятая: `3/4 → "0,75"`, `3/2 → "1,5"`.
- Диапазон: оба конца масштабируются и округляются до целого (half-up): `3-4 × 3/2 → "5-6"` (4.5→5). Концы — счётные предметы, дробные диапазоны нечитаемы.

### Деградация

Нет числа → строка возвращается без изменений. Это не ошибка, а честное «нет количества» («по вкусу», «щепотка», «упаковка»).

## `Recipe.format_message`

```python
def format_message(self, category_name: str | None = None, *,
                   portions_override: int | None = None) -> str:
    if portions_override and portions_override != self.portions and self.portions > 0:
        factor = Fraction(portions_override, self.portions)
        ingredients = scale_ingredients(self.ingredients, factor)
    else:
        ingredients = self.ingredients
    # дальше как раньше, но из ingredients (масштабированных)
    # КБЖУ-строка (_nutrition_line) НЕ меняется — остаётся на self.portions
```

КБЖУ намеренно не трогается (решение explore-режима): значения на порцию математически инвариантны, подпись остаётся с базовым числом порций.

## Клавиатура и состояние

Stateless — текущее число порций кодируется в `callback_data`, кэш **не мутируется**:

```
   [psc:{rk}:3]  [ 4 порции ]  [psc:{rk}:5]
                                       │ click
                                       ▼
   handler: cache.get(rk) → {recipe_id, group_id}
            recipe = from_markdown(...)
            factor = Fraction(5, recipe.portions)   # 5/4
            edit_text(format_message(portions_override=5),
                      reply_markup=recipe_keyboard(..., current_portions=5))
            │ новый rk (put_recipe внутри) → новое состояние в callback_data
            ▼
   [psc:{rk_new}:4]  [ 5 порций ]  [psc:{rk_new}:6]
```

`recipe_keyboard` расширяется опциональными `base_portions`/`current_portions`: при `base_portions > 0` добавляет ряд порций; границы 1..20 скрывают соответствующую кнопку. `rk` генерируется один раз на рендер (как сейчас) и используется во всех кнопках ряда.

## Хендлер `psc:`

```python
@router.callback_query(F.data.startswith("psc:"))
async def handle_portions_change(callback):
    rk, target = _parse_psc(callback)        # psc:{rk}:{target}, target clamped 1..20
    cached = cache.get(rk)
    recipe = Recipe.from_markdown(...)
    await callback.message.edit_text(
        recipe.format_message(category_name, portions_override=target),
        reply_markup=recipe_keyboard(recipe_id, group_id,
                                     base_portions=recipe.portions,
                                     current_portions=target,
                                     source_url=source_url))
```

## Границы и инварианты

- `base_portions == 0`: ряд порций не показывается (не на что делить).
- `target == base`: factor = 1, строки пересобираются, но визуально равны исходным.
- `target` всегда в 1..20 (clamp на входе хендлера — защита от подделанного callback_data).
- Кэш `rk` протухнет через час (существующий TTL) — кнопка покажет «данные устарели».

## Что НЕ меняется

| Компонент | Почему |
|---|---|
| БД / схема | пересчёт эфемерен, в `content_md` ничего не пишем |
| `recipe_parser.py` / промпты | источник `portions` и ингредиентов прежний |
| `recipe_pipeline.py` / `group_manager.py` | на уровень ниже |
| КБЖУ | решено не трогать |
| `format_markdown_for_chat` / дашборд | вне MVP |

## Риски

| Риск | Митигация |
|---|---|
| Regex не ловит редкую форму | Ингредиент без числа выводится как есть (деградация, не ошибка) |
| Подделанное `target` в callback | clamp в 1..20 на входе хендлера |
| Быстрые двойные клики | Telegram блокирует concurrent edits одного сообщения; idempotent по `target` |
| float-грязь | `fractions.Fraction` для точной арифметики |
| `rk` протух | стандартное «данные устарели», как у других кнопок |

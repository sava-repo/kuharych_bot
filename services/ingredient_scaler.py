"""Пересчёт количества ингредиентов на выбранное число порций.

Ингредиенты хранятся свободным текстом (``list[str]``); ведущее число
(целое / десятичное / дробь / смешанная дробь / диапазон) масштабируется
на коэффициент ``factor`` через :class:`fractions.Fraction`. Ингредиенты
без ведущего числа («по вкусу», «щепотка») возвращаются без изменений.
"""

import re
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction

# Паттерны проверяются по порядку — длинное совпадение первым (якорь в начале).
_MIXED = re.compile(r"^(\d+)\s+(\d+)/(\d+)")     # 1 1/2
_RANGE = re.compile(r"^(\d+)\s*[-\u2013\u2014]\s*(\d+)")  # 3-4 / 3–4 / 3—4
_FRACTION = re.compile(r"^(\d+)/(\d+)")          # 1/2
_DECIMAL = re.compile(r"^(\d+)[.,](\d+)")        # 1.5 / 1,5
_INT = re.compile(r"^(\d+)")                     # 400


def scale_ingredients(ingredients: list[str], factor: Fraction) -> list[str]:
    """Масштабирует ведущее число в каждой строке списка; без числа — как есть."""
    return [scale_ingredient(ing, factor) for ing in ingredients]


def scale_ingredient(ingredient: str, factor: Fraction) -> str:
    """Масштабирует ведущее число в строке ингредиента на ``factor`` (>0).

    Возвращает исходную строку, если числа в начале нет.
    """
    if not ingredient:
        return ingredient

    # Смешанная дробь: 1 1/2 → Fraction(1) + Fraction(1,2)
    m = _MIXED.match(ingredient)
    if m:
        whole, num, den = int(m[1]), int(m[2]), int(m[3])
        if den == 0:
            return ingredient
        scaled = (Fraction(whole) + Fraction(num, den)) * factor
        return _replace_prefix(ingredient, m, _format_decimal(scaled))

    # Диапазон: 3-4 → оба конца масштабируются и округляются до целого
    m = _RANGE.match(ingredient)
    if m:
        low, high = Fraction(int(m[1])), Fraction(int(m[2]))
        return _replace_prefix(ingredient, m, f"{_round_int(low * factor)}-{_round_int(high * factor)}")

    # Обычная дробь: 1/2
    m = _FRACTION.match(ingredient)
    if m:
        num, den = int(m[1]), int(m[2])
        if den == 0:
            return ingredient
        scaled = Fraction(num, den) * factor
        return _replace_prefix(ingredient, m, _format_decimal(scaled))

    # Десятичная: 1.5 / 1,5
    m = _DECIMAL.match(ingredient)
    if m:
        scaled = Fraction(Decimal(f"{m[1]}.{m[2]}")) * factor
        return _replace_prefix(ingredient, m, _format_decimal(scaled))

    # Целое: 400
    m = _INT.match(ingredient)
    if m:
        scaled = Fraction(int(m[1])) * factor
        return _replace_prefix(ingredient, m, _format_decimal(scaled))

    return ingredient


def _replace_prefix(ingredient: str, match: re.Match, new_prefix: str) -> str:
    """Заменяет сматченную числовую часть на ``new_prefix``, сохраняя остаток."""
    return new_prefix + ingredient[match.end():]


def _format_decimal(f: Fraction) -> str:
    """Форматирует Fraction как строку: целый → ``str(int)``;
    дробный → округление до 2 знаков (half-up), без хвостовых нулей, русская запятая.
    """
    if f.denominator == 1:
        return str(f.numerator)
    d = Decimal(f.numerator) / Decimal(f.denominator)
    rounded = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = format(rounded, "f").rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _round_int(f: Fraction) -> int:
    """Округление Fraction до целого (half-up)."""
    d = Decimal(f.numerator) / Decimal(f.denominator)
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

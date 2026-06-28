"""Unit tests for services/ingredient_scaler.py"""
from fractions import Fraction

from services.ingredient_scaler import scale_ingredient, scale_ingredients


F3_2 = Fraction(3, 2)
F2 = Fraction(2)


class TestScaleInteger:
    def test_integer_value(self):
        assert scale_ingredient("400", F3_2) == "600"

    def test_integer_with_unit(self):
        assert scale_ingredient("400 г говядины", F3_2) == "600 г говядины"

    def test_count_items(self):
        assert scale_ingredient("2 яйца", F3_2) == "3 яйца"


class TestScaleDecimal:
    def test_comma_decimal(self):
        assert scale_ingredient("1,5 стакана", F3_2) == "2,25 стакана"

    def test_dot_decimal(self):
        assert scale_ingredient("1.5 стакана", F3_2) == "2,25 стакана"


class TestScaleFraction:
    def test_simple_fraction(self):
        # 1/2 × 3/2 = 3/4 = 0,75
        assert scale_ingredient("1/2 ч. л. соли", F3_2) == "0,75 ч. л. соли"


class TestScaleMixedFraction:
    def test_mixed_fraction(self):
        # 1 1/2 × 2 = 3
        assert scale_ingredient("1 1/2 стакана", F2) == "3 стакана"


class TestScaleRange:
    def test_range_both_ends(self):
        # 3-4 × 3/2 → 4,5-6 → 5-6 (half-up)
        assert scale_ingredient("3-4 зубчика", F3_2) == "5-6 зубчика"

    def test_range_dash_variants(self):
        assert scale_ingredient("3-4 зубчика", F2) == "6-8 зубчика"


class TestNoNumber:
    def test_no_number_unchanged(self):
        assert scale_ingredient("по вкусу соль", F3_2) == "по вкусу соль"

    def test_word_quantity_unchanged(self):
        assert scale_ingredient("щепотка перца", F3_2) == "щепотка перца"

    def test_empty_string(self):
        assert scale_ingredient("", F3_2) == ""


class TestScaleList:
    def test_list_mixed(self):
        result = scale_ingredients(
            ["400 г говядины", "по вкусу соль", "2 яйца"], F3_2)
        assert result == ["600 г говядины", "по вкусу соль", "3 яйца"]

    def test_factor_one_preserves(self):
        # factor == 1: числа пересчитываются тривиально (как есть)
        result = scale_ingredients(["400 г говядины"], Fraction(1))
        assert result == ["400 г говядины"]


class TestFormatting:
    def test_decimal_russian_comma(self):
        # 3/2 × 1/2 = 3/4 → 0,75 (не точка)
        assert "," in scale_ingredient("1/2", Fraction(3, 2))

    def test_no_trailing_zeros(self):
        # 1 × 1/2 = 0,5 (не 0,50)
        assert scale_ingredient("1", Fraction(1, 2)) == "0,5"

    def test_zero_denominator_left_unchanged(self):
        # Защита от деления на ноль в дроби
        assert scale_ingredient("1/0 чего-то", F2) == "1/0 чего-то"

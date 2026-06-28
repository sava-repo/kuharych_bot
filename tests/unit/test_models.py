"""Unit tests for models (Recipe, Group)"""
import pytest
from models.recipe import Recipe
from models.group import Group


class TestRecipeSlug:
    """Tests for Recipe.slug property"""

    def test_slug_simple_title(self):
        """Generate slug from simple Russian title"""
        recipe = Recipe(
            title="Мама мыла раму",
            ingredients=["Мама", "Мыла", "Раму"],
            steps=["Помыли раму"],
            category="основное блюдо",
            source="instagram"
        )
        assert recipe.slug == "mama-myla-ramu"

    def test_slug_with_special_characters(self):
        """Generate slug with special characters"""
        recipe = Recipe(
            title="Паста Карбонара!!!",
            ingredients=["Спагетти", "Бекон"],
            steps=["Смешать всё"],
            category="основное блюдо",
            source="instagram"
        )
        assert recipe.slug == "pasta-karbonara"

    def test_slug_with_multiple_spaces(self):
        """Generate slug with multiple consecutive spaces"""
        recipe = Recipe(
            title="Сырная  пицца",
            ingredients=["Сыр", "Тесто"],
            steps=["Испечь"],
            category="основное блюдо",
            source="instagram"
        )
        assert recipe.slug == "syrnaya-pizza"

    def test_slug_with_numbers(self):
        """Generate slug with numbers"""
        recipe = Recipe(
            title="Борщ №1",
            ingredients=["Свекла", "Капуста"],
            steps=["Варить"],
            category="основное блюдо",
            source="instagram"
        )
        assert recipe.slug == "borsh-1"

    def test_slug_english_title(self):
        """Generate slug from English title"""
        recipe = Recipe(
            title="Chocolate Cake",
            ingredients=["Chocolate", "Flour"],
            steps=["Bake"],
            category="десерт",
            source="instagram"
        )
        assert recipe.slug == "chocolate-cake"

    def test_slug_trims_dashes(self):
        """Slug should not start or end with dashes"""
        recipe = Recipe(
            title="!!!Test Recipe!!!",
            ingredients=["Test"],
            steps=["Test"],
            category="основное блюдо",
            source="instagram"
        )
        assert recipe.slug == "test-recipe"


class TestRecipeToMarkdown:
    """Tests for Recipe.to_markdown() method"""

    def test_to_markdown_basic(self):
        """Serialize recipe to markdown format"""
        recipe = Recipe(
            title="Омлет",
            ingredients=["Яйца 2 шт", "Молоко 50 мл"],
            steps=["Взбить яйца с молоком", "Жарить на сковороде"],
            category="завтрак",
            source="instagram",
            tags=["быстро", "просто"]
        )
        
        result = recipe.to_markdown(created="2024-01-01")

        assert 'title: "Омлет"' in result
        assert 'category:' not in result  # категория не атрибут рецепта
        assert 'source: "instagram"' in result
        assert 'created: "2024-01-01"' in result
        assert '"быстро", "просто"' in result
        assert "# Омлет" in result
        assert "## Ингредиенты" in result
        assert "- Яйца 2 шт" in result
        assert "## Способ приготовления" in result
        assert "1. Взбить яйца с молоком" in result
        assert "2. Жарить на сковороде" in result

    def test_to_markdown_without_tags(self):
        """Serialize recipe without tags"""
        recipe = Recipe(
            title="Суп",
            ingredients=["Вода", "Картофель"],
            steps=["Варить"],
            category="основное блюдо",
            source="instagram"
        )
        
        result = recipe.to_markdown(created="2024-01-01")
        
        assert "tags: []" in result


class TestRecipeFromJson:
    """Tests for Recipe deserialization (if method exists)"""

    @pytest.mark.skip(reason="from_json method not implemented yet")
    def test_from_json_valid(self):
        """Deserialize recipe from valid JSON"""
        json_data = {
            "title": "Плов",
            "ingredients": ["Рис", "Мясо", "Морковь"],
            "steps": ["Обжарить", "Тушить"],
            "category": "основное блюдо",
            "source": "instagram",
            "tags": ["узбекская кухня"]
        }
        
        recipe = Recipe.from_json(json_data)
        
        assert recipe.title == "Плов"
        assert recipe.ingredients == ["Рис", "Мясо", "Морковь"]
        assert recipe.category == "основное блюдо"
        assert recipe.tags == ["узбекская кухня"]


class TestRecipeNutritionMessage:
    """Tests for КБЖУ line in format_message"""

    def test_nutrition_line_shown_with_values(self):
        """При calories>0 выводится строка КБЖУ с делением на порции"""
        recipe = Recipe(
            title="Борщ",
            ingredients=["Свекла 400г"],
            steps=["Варить"],
            source="instagram",
            portions=4,
            calories=1280,
            protein=80,
            fat=40,
            carbs=120,
        )
        msg = recipe.format_message()
        assert "≈320 ккал" in msg
        assert "Б 20" in msg
        assert "Ж 10" in msg
        assert "У 30" in msg
        assert "(1 порция из 4)" in msg

    def test_nutrition_line_single_portion(self):
        """При portions==1 используется «на 1 порцию»"""
        recipe = Recipe(
            title="Омлет",
            ingredients=["Яйца 2 шт"],
            steps=["Жарить"],
            source="instagram",
            portions=1,
            calories=500,
            protein=30,
            fat=20,
            carbs=40,
        )
        msg = recipe.format_message()
        assert "(на 1 порцию)" in msg
        assert "≈500 ккал" in msg

    def test_no_nutrition_line_when_calories_zero(self):
        """При calories==0 строка КБЖУ не выводится"""
        recipe = Recipe(
            title="Суп",
            ingredients=["Вода"],
            steps=["Варить"],
            source="instagram",
        )
        msg = recipe.format_message()
        assert "ккал" not in msg
        assert "≈" not in msg

    def test_no_nutrition_line_when_portions_zero(self):
        """При portions==0 (даже если calories>0) строка не выводится"""
        recipe = Recipe(
            title="Суп",
            ingredients=["Вода"],
            steps=["Варить"],
            source="instagram",
            portions=0,
            calories=500,
        )
        msg = recipe.format_message()
        assert "ккал" not in msg

    def test_nutrition_integer_floor_division(self):
        """Деление total/portions — целочисленное (вниз)"""
        recipe = Recipe(
            title="Х",
            ingredients=["а"],
            steps=["б"],
            source="instagram",
            portions=3,
            calories=1000,
            protein=100,
            fat=10,
            carbs=10,
        )
        msg = recipe.format_message()
        assert "≈333 ккал" in msg  # 1000 // 3
        assert "Б 33" in msg       # 100 // 3


class TestRecipeNutritionMarkdown:
    """Tests for КБЖУ round-trip via to_markdown/from_markdown"""

    def test_to_markdown_writes_nutrition(self):
        recipe = Recipe(
            title="Омлет",
            ingredients=["Яйца 2 шт"],
            steps=["Жарить"],
            source="instagram",
            portions=2,
            calories=500,
            protein=30,
            fat=20,
            carbs=40,
        )
        md = recipe.to_markdown(created="2024-01-01")
        assert "portions: 2" in md
        assert "calories: 500" in md
        assert "protein: 30" in md
        assert "fat: 20" in md
        assert "carbs: 40" in md

    def test_roundtrip_preserves_nutrition(self):
        recipe = Recipe(
            title="Омлет",
            ingredients=["Яйца 2 шт"],
            steps=["Жарить"],
            source="instagram",
            tags=["быстро"],
            portions=4,
            calories=1280,
            protein=80,
            fat=40,
            carbs=120,
        )
        md = recipe.to_markdown(created="2024-01-01")
        restored = Recipe.from_markdown(md, "instagram")
        assert restored.portions == 4
        assert restored.calories == 1280
        assert restored.protein == 80
        assert restored.fat == 40
        assert restored.carbs == 120
        assert restored.tags == ["быстро"]

    def test_from_markdown_without_nutrition_defaults_zero(self):
        """Старый frontmatter без блока КБЖУ даёт поля 0 без ошибок"""
        md = (
            "---\n"
            'title: "Суп"\n'
            'source: "instagram"\n'
            'created: "2024-01-01"\n'
            'tags: ["просто"]\n'
            "---\n\n"
            "# Суп\n\n"
            "## Ингредиенты\n- Вода\n\n"
            "## Способ приготовления\n1. Варить\n"
        )
        recipe = Recipe.from_markdown(md, "instagram")
        assert recipe.portions == 0
        assert recipe.calories == 0
        assert recipe.protein == 0
        assert recipe.fat == 0
        assert recipe.carbs == 0
        assert recipe.title == "Суп"
        assert recipe.tags == ["просто"]

    def test_from_markdown_tolerates_non_numeric_nutrition(self):
        """Не-числовые значения КБЖУ дают 0"""
        md = (
            "---\n"
            'title: "Суп"\n'
            'source: "instagram"\n'
            'created: ""\n'
            'tags: []\n'
            "portions: много\n"
            "calories: нисколько\n"
            "---\n\n"
            "# Суп\n\n"
            "## Ингредиенты\n- Вода\n\n"
            "## Способ приготовления\n1. Варить\n"
        )
        recipe = Recipe.from_markdown(md, "instagram")
        assert recipe.portions == 0
        assert recipe.calories == 0


class TestRecipePortionsOverride:
    """Tests for format_message portions_override (пересчёт ингредиентов)"""

    def _recipe(self, portions=4):
        return Recipe(
            title="Борщ",
            ingredients=["400 г говядины", "по вкусу соль"],
            steps=["Варить"],
            source="ig",
            portions=portions,
            calories=1280,
            protein=80,
            fat=40,
            carbs=120,
        )

    def test_override_scales_ingredients(self):
        """portions_override=6 (base 4) → коэффициент 3/2 → 600 г говядины"""
        recipe = self._recipe(portions=4)
        msg = recipe.format_message(portions_override=6)
        assert "600 г говядины" in msg
        assert "по вкусу соль" in msg  # без числа — не меняется

    def test_override_decreases_ingredients(self):
        """portions_override=3 (base 4) → коэффициент 3/4 → 300 г говядины"""
        recipe = self._recipe(portions=4)
        msg = recipe.format_message(portions_override=3)
        assert "300 г говядины" in msg

    def test_no_override_keeps_original(self):
        """Без override — исходные ингредиенты"""
        recipe = self._recipe(portions=4)
        msg = recipe.format_message()
        assert "400 г говядины" in msg

    def test_override_equal_to_base_no_change(self):
        """portions_override == portions — без изменений"""
        recipe = self._recipe(portions=4)
        msg = recipe.format_message(portions_override=4)
        assert "400 г говядины" in msg

    def test_nutrition_line_unchanged_with_override(self):
        """КБЖУ-строка остаётся на базовом числе порций"""
        recipe = self._recipe(portions=4)
        msg = recipe.format_message(portions_override=6)
        # КБЖУ на порцию = 1280/4 = 320; подпись остаётся «1 порция из 4»
        assert "≈320 ккал" in msg
        assert "(1 порция из 4)" in msg

    def test_override_ignored_when_base_zero(self):
        """При base portions==0 override игнорируется"""
        recipe = self._recipe(portions=0)
        msg = recipe.format_message(portions_override=6)
        assert "400 г говядины" in msg  # без пересчёта

    def test_steps_unchanged_with_override(self):
        """Способ приготовления не меняется при пересчёте"""
        recipe = self._recipe(portions=4)
        msg = recipe.format_message(portions_override=6)
        assert "1. Варить" in msg


class TestGroupIsPersonal:
    """Tests for Group.is_personal property"""

    def test_is_personal_true(self):
        """Detect personal group by 'pers_' prefix"""
        group = Group(
            group_id="pers_123",
            name="Personal",
            owner_id=252952086,
            members=[252952086]
        )
        assert group.is_personal is True

    def test_is_personal_false(self):
        """Detect non-personal group"""
        group = Group(
            group_id="grp_abc123",
            name="Family",
            owner_id=252952086,
            members=[252952086, 999999999]
        )
        assert group.is_personal is False

    def test_is_personal_empty_group_id(self):
        """Handle empty group_id"""
        group = Group(
            group_id="",
            name="Empty",
            owner_id=252952086,
            members=[]
        )
        assert group.is_personal is False

    def test_is_personal_pers_in_middle(self):
        """'pers_' must be at the start"""
        group = Group(
            group_id="group_pers_test",
            name="Test",
            owner_id=252952086,
            members=[252952086]
        )
        assert group.is_personal is False
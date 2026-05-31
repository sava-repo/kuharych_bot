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
        assert 'category: "завтрак"' in result
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
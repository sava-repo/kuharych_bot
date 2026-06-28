"""Unit tests for recipe parser service"""
import pytest
from services.recipe_parser import (
    _build_user_prompt,
    _parse_recipe_response,
    _generate_tags,
    NotARecipeError,
    RecipeParseError,
)


class TestBuildUserPrompt:
    """Tests for _build_user_prompt function"""

    def test_with_both_transcription_and_caption(self):
        """Build prompt with both transcription and caption"""
        result = _build_user_prompt(
            transcription="Test transcription",
            caption="Test caption"
        )
        assert "Транскрибация видео:" in result
        assert "Test transcription" in result
        assert "Описание под видео:" in result
        assert "Test caption" in result

    def test_with_caption_only_fallback(self):
        """Build prompt with only caption (transcription fallback mode)"""
        result = _build_user_prompt(
            transcription=None,
            caption="Test caption"
        )
        assert "Транскрибация видео недоступна" in result
        assert "Test caption" in result

    def test_with_none_caption_fallback(self):
        """Build prompt with None caption (transcription fallback mode)"""
        result = _build_user_prompt(
            transcription=None,
            caption=None
        )
        assert "Транскрибация видео недоступна" in result
        assert "(нет описания)" in result

    def test_with_empty_transcription_and_caption(self):
        """Build prompt with empty transcription but has caption"""
        result = _build_user_prompt(
            transcription=None,
            caption=""
        )
        assert "Транскрибация видео недоступна" in result
        assert "(нет описания)" in result


class TestGenerateTags:
    """Tests for _generate_tags function"""

    def test_generate_tags_from_title(self):
        """Generate tags from title words"""
        tags = _generate_tags("Паста Карбонара", [])
        assert "паста" in tags
        assert "карбонара" in tags

    def test_generate_tags_from_ingredients(self):
        """Generate tags from ingredient names"""
        tags = _generate_tags(
            "Борщ",
            ["Свекла 2 шт", "Капуста 300г", "Мясо 500г"]
        )
        assert "свекла" in tags
        assert "капуста" in tags
        assert "мясо" in tags

    def test_generate_tags_combined(self):
        """Generate tags from both title and ingredients"""
        tags = _generate_tags(
            "Оливье",
            ["Картофель", "Морковь", "Яйца", "Горошек"]
        )
        assert "оливье" in tags
        assert "картофель" in tags
        assert "морковь" in tags

    def test_generate_tags_filters_short_words(self):
        """Filter out words shorter than 3 characters"""
        tags = _generate_tags("С А", ["Вода", "Соль"])
        # "С" and "А" are too short, should be filtered
        assert all(len(tag) > 2 for tag in tags)

    def test_generate_tags_limits_to_10(self):
        """Limit tags to maximum 10"""
        tags = _generate_tags(
            "Длинное название",
            ["Ингредиент1", "Ингредиент2", "Ингредиент3", 
             "Ингредиент4", "Ингредиент5", "Ингредиент6",
             "Ингредиент7", "Ингредиент8", "Ингредиент9"]
        )
        assert len(tags) <= 10

    def test_generate_tags_removes_punctuation(self):
        """Remove punctuation from tags"""
        tags = _generate_tags("Салат, с огурцом!", ["Помидоры.", "Масло?"])
        assert all("," not in tag for tag in tags)
        assert all("!" not in tag for tag in tags)
        assert all("." not in tag for tag in tags)
        assert all("?" not in tag for tag in tags)


class TestParseRecipeResponse:
    """Tests for _parse_recipe_response function"""

    def test_parse_valid_recipe_response(self):
        """Parse valid LLM response with all fields"""
        response_text = """
Название: Паста Карбонара

Категория: основное блюдо

Ингредиенты:
- Спагетти 400г
- Бекон 200г
- Яйца 4 шт
- Пармезан 100г

Способ приготовления:
Шаг 1: Отварите спагетти до аль денте
Шаг 2: Обжарьте бекон до хруста
Шаг 3: Смешайте яйца с пармезаном
Шаг 4: Соедините все ингредиенты и подавайте
"""
        
        recipe = _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        
        assert recipe.title == "Паста Карбонара"
        assert recipe.category == "основное блюдо"
        assert len(recipe.ingredients) == 4
        assert "Спагетти 400г" in recipe.ingredients
        assert len(recipe.steps) == 4
        assert "Отварите спагетти до аль денте" in recipe.steps
        assert recipe.source == "instagram"

    def test_parse_response_with_numbers_steps(self):
        """Parse response with numbered steps (1., 2., etc.)"""
        response_text = """
Название: Борщ

Ингредиенты:
- Свекла
- Капуста

Способ приготовления:
1. Нарезать овощи
2. Варить 1 час
"""
        
        recipe = _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        
        assert recipe.title == "Борщ"
        assert len(recipe.steps) == 2
        assert "Нарезать овощи" in recipe.steps
        assert "Варить 1 час" in recipe.steps

    def test_parse_without_explicit_category(self):
        """Parse response without category (uses default)"""
        response_text = """
Название: Омлет

Ингредиенты:
- Яйца 2 шт

Способ приготовления:
Шаг 1: Взбить яйца
Шаг 2: Жарить
"""
        
        recipe = _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        
        assert recipe.category == "основное блюдо"

    def test_not_a_recipe_error(self):
        """Raise NotARecipeError when response indicates not a recipe"""
        response_text = """
Название: Это не рецепт

Категория: другое

Ингредиенты:
- Нет ингредиентов

Способ приготовления:
- НЕ РЕЦЕПТ
"""
        
        with pytest.raises(NotARecipeError) as exc_info:
            _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        
        assert "не содержит рецепт" in str(exc_info.value).lower()

    def test_parse_error_missing_title(self):
        """Raise RecipeParseError when title is missing"""
        response_text = """
Ингредиенты:
- Яйца

Способ приготовления:
Шаг 1: Жарить
"""
        
        with pytest.raises(RecipeParseError) as exc_info:
            _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        
        assert "название" in str(exc_info.value).lower()

    def test_parse_error_missing_ingredients(self):
        """Raise RecipeParseError when ingredients are missing"""
        response_text = """
Название: Блюдо

Способ приготовления:
Шаг 1: Готовить
"""
        
        with pytest.raises(RecipeParseError) as exc_info:
            _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        
        assert "ингредиенты" in str(exc_info.value).lower()

    def test_parse_error_missing_steps(self):
        """Raise RecipeParseError when steps are missing"""
        response_text = """
Название: Блюдо

Ингредиенты:
- Ингредиент
"""
        
        with pytest.raises(RecipeParseError) as exc_info:
            _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        
        assert "шаг" in str(exc_info.value).lower() or "способ" in str(exc_info.value).lower()

    def test_malformed_json_like_response(self, sample_malformed_json_response):
        """Handle malformed JSON-like LLM response"""
        # This test documents the behavior with malformed responses
        # The parser should try to extract data even from non-JSON text
        response_text = """
Название: Тест
Ингредиенты:
- Ингредиент 1
Способ приготовления:
Шаг 1: Сделать это
"""
        
        # This should work (text format, not JSON)
        recipe = _parse_recipe_response(response_text, "instagram", ["завтрак", "основное блюдо", "десерт"], "основное блюдо")
        assert recipe.title == "Тест"

    def test_empty_response(self):
        """Handle empty response text"""
        with pytest.raises(RecipeParseError):
            _parse_recipe_response("", "instagram", ["основное блюдо"], "основное блюдо")

    def test_whitespace_only_response(self):
        """Handle whitespace-only response"""
        with pytest.raises(RecipeParseError):
            _parse_recipe_response("   \n\n   ", "instagram", ["основное блюдо"], "основное блюдо")


class TestDynamicCategories:
    """Категории выбираются из списка активной группы; fallback на default."""

    def test_custom_category_matched(self):
        """LLM-ответ с кастомной категорией пользователя матчится."""
        response = (
            "Название: Суп\n\n"
            "Ингредиенты:\n- Вода\n\n"
            "Способ приготовления:\nШаг 1: Варить\n\n"
            "Категория: первые блюда\n"
        )
        recipe = _parse_recipe_response(
            response, "src", ["первые блюда", "на праздник"], "первые блюда"
        )
        assert recipe.category == "первые блюда"

    def test_unknown_category_falls_back_to_default(self):
        """Категория вне списка пользователя → default."""
        response = (
            "Название: Суп\n\n"
            "Ингредиенты:\n- Вода\n\n"
            "Способ приготовления:\nШаг 1: Варить\n\n"
            "Категория: неведомая\n"
        )
        recipe = _parse_recipe_response(
            response, "src", ["первые блюда", "на праздник"], "на праздник"
        )
        assert recipe.category == "на праздник"

    def test_missing_category_line_uses_default(self):
        response = (
            "Название: Суп\n\n"
            "Ингредиенты:\n- Вода\n\n"
            "Способ приготовления:\nШаг 1: Варить\n"
        )
        recipe = _parse_recipe_response(
            response, "src", ["завтрак", "на праздник"], "на праздник"
        )
        assert recipe.category == "на праздник"


class TestNutritionExtraction:
    """Извлечение КБЖУ и порций из ответа LLM."""

    def test_parse_nutrition_block(self):
        response = (
            "Название: Борщ\n\n"
            "Ингредиенты:\n- Свекла 400г\n\n"
            "Способ приготовления:\nШаг 1: Варить\n\n"
            "Категория: основное блюдо\n\n"
            "Порции: 4\n"
            "Калории: 1280\n"
            "Белки: 80\n"
            "Жиры: 40\n"
            "Углеводы: 120\n"
        )
        recipe = _parse_recipe_response(
            response, "src", ["основное блюдо"], "основное блюдо"
        )
        assert recipe.portions == 4
        assert recipe.calories == 1280
        assert recipe.protein == 80
        assert recipe.fat == 40
        assert recipe.carbs == 120

    def test_parse_nutrition_with_units(self):
        """Значения с единицами («1280 ккал», «80 г») парсятся до числа"""
        response = (
            "Название: Борщ\n\n"
            "Ингредиенты:\n- Свекла\n\n"
            "Способ приготовления:\nШаг 1: Варить\n\n"
            "Категория: основное блюдо\n\n"
            "Порции: 4 порции\n"
            "Калории: 1280 ккал\n"
            "Белки: 80 г\n"
            "Жиры: 40 грамм\n"
            "Углеводы: 120 г\n"
        )
        recipe = _parse_recipe_response(
            response, "src", ["основное блюдо"], "основное блюдо"
        )
        assert recipe.portions == 4
        assert recipe.calories == 1280
        assert recipe.protein == 80
        assert recipe.fat == 40
        assert recipe.carbs == 120

    def test_nutrition_absent_defaults_zero(self):
        """Отсутствие блока КБЖУ → поля 0, парсинг не падает"""
        response = (
            "Название: Борщ\n\n"
            "Ингредиенты:\n- Свекла\n\n"
            "Способ приготовления:\nШаг 1: Варить\n\n"
            "Категория: основное блюдо\n"
        )
        recipe = _parse_recipe_response(
            response, "src", ["основное блюдо"], "основное блюдо"
        )
        assert recipe.portions == 0
        assert recipe.calories == 0
        assert recipe.protein == 0
        assert recipe.fat == 0
        assert recipe.carbs == 0

    def test_nutrition_non_numeric_defaults_zero(self):
        """Не-числовые значения КБЖУ → поля 0"""
        response = (
            "Название: Борщ\n\n"
            "Ингредиенты:\n- Свекла\n\n"
            "Способ приготовления:\nШаг 1: Варить\n\n"
            "Категория: основное блюдо\n\n"
            "Порции: много\n"
            "Калории: неизвестно\n"
        )
        recipe = _parse_recipe_response(
            response, "src", ["основное блюдо"], "основное блюдо"
        )
        assert recipe.portions == 0
        assert recipe.calories == 0
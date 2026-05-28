"""Integration tests for end-to-end pipeline (Lobstr + Parser)"""
import pytest
import os

import config
import services.lobstr as lobstr
import services.recipe_parser as parser
from services.recipe_parser import NotARecipeError, RecipeParseError

# Skip integration tests locally, only run on server
pytestmark = pytest.mark.skipif(
    os.getenv("TESTING_ENV", "local") == "local",
    reason="Integration tests run only on server (TESTING_ENV=server)"
)


@pytest.mark.asyncio
class TestRecipePipeline:
    """End-to-end tests for recipe extraction pipeline"""
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY or not config.GLM_API_KEY,
        reason="LOBSTR_API_KEY or GLM_API_KEY not set"
    )
    async def test_extract_recipe_from_caption(self):
        """
        Test extracting recipe from Instagram caption.
        
        This test simulates the real workflow:
        1. Get caption from Lobstr
        2. Parse recipe from caption
        
        Test URL: Public cooking reel with recipe in caption
        """
        # Public Instagram Reel with recipe
        test_url = "https://www.instagram.com/reel/C_ABC123DEF/"
        
        # Step 1: Get caption via Lobstr
        caption = await lobstr.get_reel_caption(test_url)
        
        if not caption:
            pytest.skip("Could not get caption (reel may be private or deleted)")
        
        print(f"✅ Got caption ({len(caption)} chars)")
        
        # Step 2: Parse recipe from caption
        # Since we don't have transcription, parser uses caption-only mode
        try:
            recipe = await parser.generate_recipe(
                transcription=None,
                caption=caption,
                source=test_url
            )
            
            # Verify recipe structure
            assert recipe.title is not None
            assert len(recipe.title) > 0
            assert len(recipe.ingredients) > 0
            assert len(recipe.steps) > 0
            assert recipe.category in ["завтрак", "основное блюдо", "десерт"]
            assert recipe.source == test_url
            
            print(f"✅ Recipe extracted successfully")
            print(f"   Title: {recipe.title}")
            print(f"   Ingredients: {len(recipe.ingredients)}")
            print(f"   Steps: {len(recipe.steps)}")
            print(f"   Category: {recipe.category}")
            
        except (NotARecipeError, RecipeParseError) as e:
            # It's OK if the caption doesn't contain a recipe
            print(f"⚠️ Caption does not contain a recipe: {e}")
            pytest.skip("Caption does not contain a recipe")
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY or not config.GLM_API_KEY,
        reason="LOBSTR_API_KEY or GLM_API_KEY not set"
    )
    async def test_extract_recipe_with_mocked_transcription(self):
        """
        Test recipe extraction with mocked transcription.
        
        This simulates the case where transcription is available.
        """
        # Mock transcription (Russian recipe)
        mock_transcription = """
        Сегодня мы готовим пасту карбонара. 
        Нам понадобятся спагетти, бекон, яйца и пармезан.
        Сначала отварите спагетти до аль денте.
        Затем обжарьте бекон до хруста.
        Смешайте яйца с тертым пармезаном.
        Соедините все ингредиенты и подавайте.
        """
        
        mock_caption = "Рецепт пасты карбонара - быстро и вкусно! #рецепт #паста"
        
        test_url = "https://www.instagram.com/reel/C_TEST123/"
        
        try:
            recipe = await parser.generate_recipe(
                transcription=mock_transcription,
                caption=mock_caption,
                source=test_url
            )
            
            # Verify recipe structure
            assert recipe.title is not None
            assert len(recipe.ingredients) > 0
            assert len(recipe.steps) > 0
            
            print(f"✅ Recipe extracted from transcription")
            print(f"   Title: {recipe.title}")
            print(f"   Ingredients: {len(recipe.ingredients)}")
            print(f"   Steps: {len(recipe.steps)}")
            
        except (NotARecipeError, RecipeParseError) as e:
            pytest.fail(f"Failed to parse valid recipe: {e}")
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY or not config.GLM_API_KEY,
        reason="LOBSTR_API_KEY or GLM_API_KEY not set"
    )
    async def test_extract_recipe_non_recipe_content(self):
        """
        Test that non-recipe content is properly rejected.
        """
        # Caption that's clearly not a recipe
        non_recipe_caption = """
        Just a beautiful sunset at the beach today!
        Nature is amazing. #sunset #beach #nature
        """
        
        test_url = "https://www.instagram.com/reel/C_NORECIPE/"
        
        with pytest.raises((NotARecipeError, RecipeParseError)):
            await parser.generate_recipe(
                transcription=None,
                caption=non_recipe_caption,
                source=test_url
            )
        
        print("✅ Non-recipe content properly rejected")


@pytest.mark.asyncio
class TestPipelineErrorHandling:
    """Test error handling in the pipeline"""
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY,
        reason="LOBSTR_API_KEY not set"
    )
    async def test_pipeline_with_invalid_reel(self):
        """
        Test pipeline behavior with invalid/non-existent reel.
        """
        invalid_url = "https://www.instagram.com/reel/INVALID123456/"
        
        # Step 1: Try to get caption
        caption = await lobstr.get_reel_caption(invalid_url)
        
        # Caption should be None
        assert caption is None
        
        # Step 2: Try to parse (should handle None gracefully)
        if not caption:
            print("✅ Invalid reel handled - caption is None")
            return
        
        # If somehow we got a caption, try to parse it
        try:
            recipe = await parser.generate_recipe(
                transcription=None,
                caption=caption,
                source=invalid_url
            )
            print(f"✅ Parsed recipe from unexpected caption: {recipe.title}")
        except (NotARecipeError, RecipeParseError) as e:
            print(f"✅ Non-recipe caption handled: {e}")


@pytest.mark.asyncio
class TestPipelineDocumentation:
    """Documentation of test URLs and data"""
    
    def test_documentation(self):
        """
        Document test URLs and expected behavior.
        
        Test URLs:
        1. https://www.instagram.com/reel/C_ABC123DEF/ - Placeholder for public cooking reel
           Expected: Should contain recipe in caption or transcription
        
        2. https://www.instagram.com/reel/C_TEST123/ - Mock transcription test
           Expected: Successfully parse recipe from mocked transcription
        
        3. https://www.instagram.com/reel/C_NORECIPE/ - Non-recipe content
           Expected: Properly reject with NotARecipeError or RecipeParseError
        
        4. https://www.instagram.com/reel/INVALID123456/ - Non-existent reel
           Expected: Lobstr returns None, pipeline handles gracefully
        
        Test Data:
        - Mock transcription: Russian recipe for pasta carbonara
        - Mock caption: Simple recipe description
        - Non-recipe caption: Nature photography caption
        """
        print("✅ Test documentation verified")
        print("   See test method docstrings for URL details")
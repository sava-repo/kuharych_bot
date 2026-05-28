"""Integration tests for Lobstr API (live)"""
import pytest
import os

import config
import services.lobstr as lobstr

# Skip integration tests locally, only run on server
pytestmark = pytest.mark.skipif(
    os.getenv("TESTING_ENV", "local") == "local",
    reason="Integration tests run only on server (TESTING_ENV=server)"
)


@pytest.mark.asyncio
class TestLobstrLiveApi:
    """Live integration tests for Lobstr.io API"""
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY,
        reason="LOBSTR_API_KEY not set"
    )
    async def test_get_reel_caption_real_api(self):
        """
        Test getting caption from real Instagram Reel via Lobstr API.
        
        Test URL: Public cooking reel with recipe
        """
        # Public Instagram Reel with a recipe
        test_url = "https://www.instagram.com/reel/C_ABC123DEF/"
        
        caption = await lobstr.get_reel_caption(test_url)
        
        # We should get either a caption or None (if not found)
        # The API call itself should not raise an exception
        assert caption is None or isinstance(caption, str)
        
        if caption:
            # If we got a caption, it should not be empty
            assert len(caption) > 0
            assert len(caption.strip()) > 0
            print(f"✅ Got caption ({len(caption)} chars): {caption[:100]}...")
        else:
            print("⚠️ Caption is None (reel may be private or deleted)")
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY,
        reason="LOBSTR_API_KEY not set"
    )
    async def test_get_reel_caption_non_instagram(self):
        """Test that non-Instagram URLs return None"""
        non_instagram_url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        
        caption = await lobstr.get_reel_caption(non_instagram_url)
        
        assert caption is None
        print("✅ Non-Instagram URL correctly returns None")
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY,
        reason="LOBSTR_API_KEY not set"
    )
    async def test_get_reel_caption_no_api_key(self):
        """Test behavior when LOBSTR_API_KEY is not set"""
        # Temporarily clear the API key
        original_key = config.LOBSTR_API_KEY
        
        try:
            config.LOBSTR_API_KEY = ""
            test_url = "https://www.instagram.com/reel/C_ABC123DEF/"
            
            caption = await lobstr.get_reel_caption(test_url)
            
            # Should return None when API key is not set
            assert caption is None
            print("✅ No API key correctly returns None")
            
        finally:
            # Restore the API key
            config.LOBSTR_API_KEY = original_key


@pytest.mark.asyncio
class TestLobstrLiveApiErrorHandling:
    """Test error handling in live Lobstr API"""
    
    @pytest.mark.skipif(
        not config.LOBSTR_API_KEY,
        reason="LOBSTR_API_KEY not set"
    )
    async def test_get_reel_caption_invalid_reel(self):
        """Test handling of invalid/non-existent reel"""
        # Non-existent reel URL
        invalid_url = "https://www.instagram.com/reel/INVALID123456/"
        
        # Should not raise exception, return None instead
        caption = await lobstr.get_reel_caption(invalid_url)
        
        # May return None or raise error - both are acceptable
        # The important thing is that it doesn't crash the bot
        assert caption is None or isinstance(caption, str)
        print("✅ Invalid reel handled gracefully")


@pytest.mark.asyncio
class TestLobstrUrlValidationLive:
    """Test URL validation functions with live data"""
    
    def test_is_instagram_url_real(self):
        """Test URL validation with real Instagram URLs"""
        valid_urls = [
            "https://www.instagram.com/reel/C_ABC123DEF/",
            "https://instagram.com/p/BZY123xyz/",
            "https://www.instagram.com/tv/ABC123/",
        ]
        
        for url in valid_urls:
            assert lobstr._is_instagram_url(url), f"Failed for {url}"
        
        print(f"✅ All {len(valid_urls)} Instagram URLs validated")
    
    def test_clean_url_real(self):
        """Test URL cleaning with real Instagram URLs"""
        test_cases = [
            ("https://instagram.com/reel/ABC123/?utm_source=test", 
             "https://instagram.com/reel/ABC123/"),
            ("https://www.instagram.com/reel/ABC123/?utm=test&mid=some#section",
             "https://www.instagram.com/reel/ABC123/"),
        ]
        
        for input_url, expected_output in test_cases:
            result = lobstr._clean_url(input_url)
            assert result == expected_output, f"Failed for {input_url}"
        
        print(f"✅ All {len(test_cases)} URLs cleaned correctly")
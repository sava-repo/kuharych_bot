"""Unit tests for Lobstr service pure functions"""
import pytest
from services.lobstr import _is_instagram_url, _clean_url, _headers


class TestIsInstagramUrl:
    """Tests for _is_instagram_url function"""

    def test_valid_instagram_url(self):
        """Validate Instagram Reel URL"""
        url = "https://instagram.com/reel/ABC123"
        assert _is_instagram_url(url) is True

    def test_valid_instagram_url_with_www(self):
        """Validate Instagram URL with www subdomain"""
        url = "https://www.instagram.com/reel/ABC123"
        assert _is_instagram_url(url) is True

    def test_instagram_reel_url(self):
        """Validate Instagram Reel specific URL"""
        url = "https://www.instagram.com/reel/C_ABC123DEF/"
        assert _is_instagram_url(url) is True

    def test_non_instagram_url_youtube(self):
        """Reject YouTube URL"""
        url = "https://youtube.com/watch?v=123"
        assert _is_instagram_url(url) is False

    def test_non_instagram_url_facebook(self):
        """Reject Facebook URL"""
        url = "https://facebook.com/video/123"
        assert _is_instagram_url(url) is False

    def test_non_instagram_url_tiktok(self):
        """Reject TikTok URL"""
        url = "https://tiktok.com/@user/video/123"
        assert _is_instagram_url(url) is False

    def test_empty_string(self):
        """Handle empty string"""
        assert _is_instagram_url("") is False

    def test_instagram_substring_in_other_domain(self):
        """Edge case: 'instagram' in non-instagram domain"""
        # This should NOT match as it's not instagram.com domain
        url = "https://not-instagram.com/reel/ABC123"
        assert _is_instagram_url(url) is False


class TestCleanUrl:
    """Tests for _clean_url function"""

    def test_clean_url_with_query_params(self):
        """Remove query parameters from URL"""
        url = "https://instagram.com/reel/ABC123?utm_source=test"
        assert _clean_url(url) == "https://instagram.com/reel/ABC123"

    def test_clean_url_with_multiple_query_params(self):
        """Remove multiple query parameters"""
        url = "https://instagram.com/reel/ABC123?utm_source=test&utm_medium=social&campaign=food"
        assert _clean_url(url) == "https://instagram.com/reel/ABC123"

    def test_clean_url_with_fragment(self):
        """Remove fragment from URL"""
        url = "https://instagram.com/reel/ABC123#section"
        assert _clean_url(url) == "https://instagram.com/reel/ABC123"

    def test_clean_url_with_query_and_fragment(self):
        """Remove both query and fragment"""
        url = "https://instagram.com/reel/ABC123?utm=test#section"
        assert _clean_url(url) == "https://instagram.com/reel/ABC123"

    def test_clean_url_without_params(self):
        """Keep URL unchanged if no params"""
        url = "https://instagram.com/reel/ABC123"
        assert _clean_url(url) == "https://instagram.com/reel/ABC123"

    def test_clean_url_with_trailing_slash(self):
        """Preserve trailing slash"""
        url = "https://instagram.com/reel/ABC123/"
        assert _clean_url(url) == "https://instagram.com/reel/ABC123/"

    def test_clean_url_trailing_slash_with_params(self):
        """Trailing slash + params"""
        url = "https://instagram.com/reel/ABC123/?utm=test"
        assert _clean_url(url) == "https://instagram.com/reel/ABC123/"

    def test_clean_url_preserves_path(self):
        """Keep full path intact"""
        url = "https://instagram.com/p/ABC123/media/?size=l"
        assert _clean_url(url) == "https://instagram.com/p/ABC123/media/"


class TestHeaders:
    """Tests for _headers function"""

    def test_headers_structure(self):
        """Verify headers dict structure"""
        headers = _headers()
        assert isinstance(headers, dict)
        assert "Authorization" in headers

    def test_headers_format(self):
        """Verify Authorization header format"""
        headers = _headers()
        auth_value = headers["Authorization"]
        assert auth_value.startswith("Token ")
        # Format should be "Token <API_KEY>"

    def test_headers_no_api_key(self):
        """Handle missing API key"""
        # This test verifies function works even if LOBSTR_API_KEY is empty
        headers = _headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Token "
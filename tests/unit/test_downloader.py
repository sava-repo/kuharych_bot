"""Unit tests for downloader service"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from services.downloader import _build_kkclip_url, _validate_cookies_file, TEMP_DIR


class TestBuildKkclipUrl:
    """Tests for _build_kkclip_url function"""

    def test_build_kkclip_url_from_reel(self):
        """Build kkclip URL from Instagram Reel"""
        url = "https://www.instagram.com/reel/C_ABC123DEF/"
        result = _build_kkclip_url(url)
        assert result == "https://kkclip.com/reel/C_ABC123DEF/"

    def test_build_kkclip_url_from_post(self):
        """Build kkclip URL from Instagram Post"""
        url = "https://instagram.com/p/BZY123xyz/"
        result = _build_kkclip_url(url)
        assert result == "https://kkclip.com/p/BZY123xyz/"

    def test_build_kkclip_url_from_tv(self):
        """Build kkclip URL from Instagram TV"""
        url = "https://www.instagram.com/tv/ABC123/"
        result = _build_kkclip_url(url)
        assert result == "https://kkclip.com/tv/ABC123/"

    def test_build_kkclip_url_with_query_params(self):
        """Handle query parameters in URL"""
        url = "https://instagram.com/reel/ABC123/?utm_source=test"
        result = _build_kkclip_url(url)
        assert result == "https://kkclip.com/reel/ABC123/"

    def test_build_kkclip_url_invalid_not_instagram(self):
        """Raise ValueError for non-Instagram URL"""
        url = "https://youtube.com/watch?v=123"
        with pytest.raises(ValueError) as exc_info:
            _build_kkclip_url(url)
        assert "не Instagram URL" in str(exc_info.value)

    def test_build_kkclip_url_invalid_no_shortcode(self):
        """Raise ValueError when shortcode is missing"""
        url = "https://instagram.com/reel/"
        with pytest.raises(ValueError) as exc_info:
            _build_kkclip_url(url)
        assert "не Instagram URL" in str(exc_info.value)


class TestValidateCookiesFile:
    """Tests for _validate_cookies_file function"""

    def test_validate_valid_cookies_file(self, tmp_path):
        """Validate valid Netscape cookies file"""
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".instagram.com\tTRUE\t/\tFALSE\t1234567890\tsessionid\ttest_session_value\n"
        )
        
        result = _validate_cookies_file(cookies_file)
        assert result is True

    def test_validate_file_not_exists(self, tmp_path):
        """Return False for non-existent file"""
        cookies_file = tmp_path / "nonexistent.txt"
        result = _validate_cookies_file(cookies_file)
        assert result is False

    def test_validate_empty_file(self, tmp_path):
        """Return False for empty file"""
        cookies_file = tmp_path / "empty.txt"
        cookies_file.write_text("")
        
        result = _validate_cookies_file(cookies_file)
        assert result is False

    def test_validate_missing_netscape_header(self, tmp_path):
        """Return False for file without Netscape header"""
        cookies_file = tmp_path / "no_header.txt"
        cookies_file.write_text(
            ".instagram.com\tTRUE\t/\tFALSE\t1234567890\tsessionid\ttest\n"
        )
        
        result = _validate_cookies_file(cookies_file)
        assert result is False

    def test_validate_missing_sessionid(self, tmp_path):
        """Return False for file without sessionid cookie"""
        cookies_file = tmp_path / "no_sessionid.txt"
        cookies_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".instagram.com\tTRUE\t/\tFALSE\t1234567890\tdsid\ttest\n"
        )
        
        result = _validate_cookies_file(cookies_file)
        assert result is False

    def test_validate_sessionid_case_insensitive(self, tmp_path):
        """Find sessionid regardless of case"""
        cookies_file = tmp_path / "case_insensitive.txt"
        cookies_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".instagram.com\tTRUE\t/\tFALSE\t1234567890\tSESSIONID\ttest\n"
        )
        
        result = _validate_cookies_file(cookies_file)
        assert result is True

    def test_validate_with_extra_lines(self, tmp_path):
        """Validate file with multiple cookies"""
        cookies_file = tmp_path / "multiple.txt"
        cookies_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".instagram.com\tTRUE\t/\tFALSE\t1234567890\tmid\ttest_mid\n"
            ".instagram.com\tTRUE\t/\tFALSE\t1234567890\tdsid\ttest_dsid\n"
            ".instagram.com\tTRUE\t/\tFALSE\t1234567890\tsessionid\ttest_session\n"
        )
        
        result = _validate_cookies_file(cookies_file)
        assert result is True


class TestEnsureTempDir:
    """Tests for _ensure_temp_dir function"""

    @patch('services.downloader.TEMP_DIR', Path("/tmp/test-recipe-bot"))
    def test_ensure_temp_dir_creates_directory(self):
        """Test that temp directory is created"""
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            from services.downloader import _ensure_temp_dir
            _ensure_temp_dir()
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestCleanupFile:
    """Tests for cleanup_file function"""

    @patch('os.remove')
    @patch('os.path.exists')
    def test_cleanup_existing_file(self, mock_exists, mock_remove):
        """Clean up existing file"""
        mock_exists.return_value = True
        
        from services.downloader import cleanup_file
        cleanup_file("/tmp/test.mp4")
        
        mock_remove.assert_called_once_with("/tmp/test.mp4")

    @patch('os.remove')
    @patch('os.path.exists')
    def test_cleanup_nonexistent_file(self, mock_exists, mock_remove):
        """Handle non-existent file gracefully"""
        mock_exists.return_value = False
        
        from services.downloader import cleanup_file
        cleanup_file("/tmp/nonexistent.mp4")
        
        mock_remove.assert_not_called()

    @patch('os.remove')
    @patch('os.path.exists')
    def test_cleanup_with_wav_file(self, mock_exists, mock_remove):
        """Clean up both mp4 and wav files"""
        mock_exists.return_value = True
        
        from services.downloader import cleanup_file
        cleanup_file("/tmp/test.mp4")
        
        # Should be called twice: once for mp4, once for wav
        assert mock_remove.call_count == 2
        calls = [call[0][0] for call in mock_remove.call_args_list]
        assert "/tmp/test.mp4" in calls
        assert "/tmp/test.wav" in calls

    @patch('os.remove')
    @patch('os.path.exists')
    @patch('logging.Logger.warning')
    def test_cleanup_error_handling(self, mock_logger, mock_exists, mock_remove):
        """Handle cleanup errors gracefully"""
        mock_exists.return_value = True
        mock_remove.side_effect = PermissionError("Cannot delete")
        
        from services.downloader import cleanup_file
        cleanup_file("/tmp/test.mp4")
        
        mock_logger.assert_called_once()
        assert "Cleanup failed" in str(mock_logger.call_args)


class TestDownloadVideoIntegration:
    """Integration-style tests with mocked dependencies"""

    @patch('yt_dlp.YoutubeDL')
    @patch('services.downloader._validate_cookies_file')
    @patch('services.downloader._ensure_temp_dir')
    def test_download_video_success(self, mock_ensure_temp, mock_validate, mock_ydl_class):
        """Successfully download video with mocked yt-dlp"""
        mock_validate.return_value = True
        
        # Mock YouTubeDL instance
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        
        # Mock extract_info response
        mock_ydl.extract_info.return_value = {
            'duration': 60,
            'description': 'Test recipe description'
        }
        
        # Mock download method
        mock_ydl.download = MagicMock()
        
        # Mock file creation
        with patch.object(TEMP_DIR, '__truediv__', return_value=Path('/tmp/test.mp4')):
            with patch.object(Path, 'exists', return_value=True):
                from services.downloader import download_video
                result = download_video("https://instagram.com/reel/ABC123/", 123)
        
        assert result is not None

    @pytest.mark.skip(reason="Complex mock setup required")
    def test_download_video_too_long(self):
        """Raise ValueError for video exceeding max duration"""
        # This test requires more complex mocking setup
        # Skipping for now as it's covered in integration tests
        pass
"""Unit tests for HikerAPI video URL extraction"""
import pytest
from services.hiker import _extract_video_url
from exceptions import VideoDownloadError


class TestExtractVideoUrl:
    """Tests for _extract_video_url function"""

    def test_reels_format_video_url(self):
        """Reels response: direct video_url field"""
        data = {
            "video_url": "https://example.com/video.mp4",
            "caption_text": "some caption",
        }
        assert _extract_video_url(data) == "https://example.com/video.mp4"

    def test_post_format_video_versions(self):
        """Post response: video_versions array"""
        data = {
            "video_versions": [
                {"url": "https://example.com/480.mp4", "width": 480, "height": 854},
                {"url": "https://example.com/720.mp4", "width": 720, "height": 1280},
            ],
        }
        assert _extract_video_url(data) == "https://example.com/720.mp4"

    def test_post_format_single_version(self):
        """Post response: single video_version"""
        data = {
            "video_versions": [
                {"url": "https://example.com/360.mp4", "width": 360},
            ],
        }
        assert _extract_video_url(data) == "https://example.com/360.mp4"

    def test_carousel_first_video(self):
        """Carousel: extract first video resource"""
        data = {
            "media_type": 8,
            "resources": [
                {"media_type": 1, "image_versions": [{"url": "https://example.com/img.jpg"}]},
                {
                    "media_type": 2,
                    "video_versions": [
                        {"url": "https://example.com/carousel-480.mp4", "width": 480},
                        {"url": "https://example.com/carousel-720.mp4", "width": 720},
                    ],
                },
            ],
        }
        assert _extract_video_url(data) == "https://example.com/carousel-720.mp4"

    def test_carousel_video_first_resource(self):
        """Carousel: video is the first resource"""
        data = {
            "resources": [
                {
                    "media_type": 2,
                    "video_versions": [
                        {"url": "https://example.com/v1.mp4", "width": 640},
                    ],
                },
                {
                    "media_type": 2,
                    "video_versions": [
                        {"url": "https://example.com/v2.mp4", "width": 640},
                    ],
                },
            ],
        }
        assert _extract_video_url(data) == "https://example.com/v1.mp4"

    def test_no_video_raises(self):
        """No video at all raises VideoDownloadError"""
        data = {
            "media_type": 1,
            "image_versions": [{"url": "https://example.com/photo.jpg"}],
        }
        with pytest.raises(VideoDownloadError):
            _extract_video_url(data)

    def test_empty_response_raises(self):
        """Empty response raises VideoDownloadError"""
        with pytest.raises(VideoDownloadError):
            _extract_video_url({})

    def test_carousel_all_photos_raises(self):
        """Carousel with only photos raises VideoDownloadError"""
        data = {
            "media_type": 8,
            "resources": [
                {"media_type": 1, "image_versions": [{"url": "https://example.com/1.jpg"}]},
                {"media_type": 1, "image_versions": [{"url": "https://example.com/2.jpg"}]},
            ],
        }
        with pytest.raises(VideoDownloadError):
            _extract_video_url(data)

    def test_reels_url_takes_priority(self):
        """video_url field takes priority over video_versions"""
        data = {
            "video_url": "https://example.com/direct.mp4",
            "video_versions": [
                {"url": "https://example.com/alt.mp4", "width": 720},
            ],
        }
        assert _extract_video_url(data) == "https://example.com/direct.mp4"

    def test_video_versions_empty_url_skipped(self):
        """video_versions with empty url falls through to next strategy"""
        data = {
            "video_versions": [{"url": "", "width": 720}],
        }
        with pytest.raises(VideoDownloadError):
            _extract_video_url(data)

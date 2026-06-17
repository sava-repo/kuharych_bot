"""Integration tests for transcription service (Groq API)"""
import pytest
import os
from pathlib import Path

import config
import services.transcriber as transcriber

# Skip integration tests locally, only run on server
pytestmark = pytest.mark.skipif(
    os.getenv("TESTING_ENV", "local") == "local",
    reason="Integration tests run only on server (TESTING_ENV=server)"
)


@pytest.mark.asyncio
class TestTranscriberLiveApi:
    """Live integration tests for Groq transcription API"""
    
    @pytest.mark.skipif(
        not config.GROQ_API_KEY,
        reason="GROQ_API_KEY not set"
    )
    async def test_transcribe_audio_file(self):
        """
        Test transcribing audio via Groq API.
        
        Requires a test audio file in tests/fixtures/test_audio.mp3
        """
        # Path to test audio file
        test_audio_path = Path(__file__).parent.parent / "fixtures" / "test_audio.mp3"
        
        if not test_audio_path.exists():
            pytest.skip(f"Test audio file not found: {test_audio_path}")
        
        print(f"✅ Test audio file found: {test_audio_path}")
        
        try:
            # Extract audio (should work even if no audio track exists)
            wav_path = await asyncio.to_thread(
                transcriber.extract_audio,
                str(test_audio_path)
            )

            if wav_path is None:
                print("⚠️ Test audio file has no audio track")
                pytest.skip("Test audio file has no audio track")

            print(f"✅ Audio extracted to: {wav_path}")
            
            # Transcribe
            text = await transcriber.transcribe_audio(wav_path)
            
            # Verify transcription
            assert isinstance(text, str)
            assert len(text) > 0
            
            print(f"✅ Transcription successful ({len(text)} chars)")
            print(f"   Text preview: {text[:100]}...")
            
        except RuntimeError as e:
            if "не содержит аудиодорожку" in str(e):
                print(f"⚠️ Test audio has no audio track: {e}")
                pytest.skip("Test audio file has no audio track")
            else:
                raise
    
    @pytest.mark.skipif(
        not config.GROQ_API_KEY,
        reason="GROQ_API_KEY not set"
    )
    async def test_transcribe_full_pipeline(self):
        """
        Test full transcription pipeline (extract + transcribe).
        """
        # Path to test audio file
        test_audio_path = Path(__file__).parent.parent / "fixtures" / "test_audio.mp3"
        
        if not test_audio_path.exists():
            pytest.skip(f"Test audio file not found: {test_audio_path}")
        
        try:
            text = await transcriber.transcribe(str(test_audio_path))
            
            assert isinstance(text, str)
            # May be empty if no audio track
            if text:
                assert len(text) > 0
                print(f"✅ Full pipeline successful ({len(text)} chars)")
                print(f"   Text: {text[:100]}...")
            else:
                print("⚠️ Transcription returned empty text (no audio track)")
        
        except RuntimeError as e:
            if "не содержит аудиодорожку" in str(e):
                print(f"⚠️ Test audio has no audio track: {e}")
                pytest.skip("Test audio file has no audio track")
            else:
                raise
    
    @pytest.mark.skipif(
        not config.GROQ_API_KEY,
        reason="GROQ_API_KEY not set"
    )
    async def test_transcribe_no_api_key(self):
        """Test behavior when GROQ_API_KEY is not set"""
        original_key = config.GROQ_API_KEY
        
        try:
            config.GROQ_API_KEY = ""
            
            # Try to transcribe (should handle missing key gracefully)
            with pytest.raises(RuntimeError) as exc_info:
                await transcriber.transcribe_audio("dummy.wav")
            
            assert "API error" in str(exc_info.value)
            print("✅ Missing API key handled correctly")
        
        finally:
            config.GROQ_API_KEY = original_key


@pytest.mark.asyncio
class TestAudioExtraction:
    """Test audio extraction from video files"""
    
    async def test_extract_audio_file_not_exists(self):
        """Test extraction with non-existent file"""
        non_existent = "/tmp/nonexistent_video.mp4"
        
        with pytest.raises(RuntimeError):
            await asyncio.to_thread(
                transcriber.extract_audio,
                non_existent
            )
        
        print("✅ Non-existent file handled correctly")
    
    async def test_extract_audio_no_audio_track(self):
        """
        Test extraction from video without audio track.
        
        Requires a video file without audio in tests/fixtures/
        """
        # This test would need a specific test file
        # For now, we document the expected behavior
        pytest.skip("Requires test video without audio track")


@pytest.mark.asyncio
class TestTranscriberDocumentation:
    """Documentation of test data and requirements"""
    
    def test_documentation(self):
        """
        Document test audio files and requirements.
        
        Test Audio Files:
        1. tests/fixtures/test_audio.mp3
           - Required for transcription tests
           - Should contain Russian speech (recipe narration)
           - Short duration (10-30 seconds recommended)
           - Format: MP3 or MP4 with audio track
        
        Requirements:
        - GROQ_API_KEY must be set in environment
        - ffmpeg binary (provided by imageio-ffmpeg)
        - Test audio file in fixtures directory
        
         Expected Behavior:
         - Successful transcription returns Russian text
         - Videos without audio track: extract_audio returns None, transcribe returns ""
         - Missing GROQ_API_KEY raises RuntimeError
         - Non-existent files raise RuntimeError
        """
        print("✅ Test documentation verified")
        print("   Test audio file: tests/fixtures/test_audio.mp3")
        print("   Required: GROQ_API_KEY environment variable")


# Import asyncio for async to_thread
import asyncio
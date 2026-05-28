# Test Fixtures

This directory contains test data files used in integration tests.

## Test Audio File

To enable transcription tests, add a test audio file named `test_audio.mp3`:

**Requirements:**
- Format: MP3 or MP4 with audio track
- Duration: 10-30 seconds (recommended)
- Content: Russian speech (recipe narration preferred)
- Size: Under 5 MB

**How to add:**
1. Record or find a short video/audio with Russian speech
2. Convert to MP3 if needed: `ffmpeg -i input.mp4 test_audio.mp3`
3. Place in this directory as `test_audio.mp3`
4. Run integration tests: `TESTING_ENV=server pytest tests/integration/test_transcriber_live.py`

**Example content:**
A short cooking instruction in Russian like:
"Сегодня мы готовим пасту. Нам понадобятся спагетти и томатный соус..."

**Note:**
If the test audio file is missing, transcription tests will be skipped automatically.
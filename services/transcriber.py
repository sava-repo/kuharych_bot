"""Извлечение аудио через ffmpeg + транскрибация через Groq Whisper API"""

import asyncio
import logging
import os
import subprocess

import httpx
import imageio_ffmpeg

import config

logger = logging.getLogger(__name__)

# Путь к бинарнику ffmpeg из imageio-ffmpeg (не требует отдельной установки)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(video_path: str) -> str | None:
    """
    Извлекает аудио из видео в WAV 16kHz mono.
    Возвращает путь к WAV файлу или None, если аудиодорожки нет.
    """
    wav_path = video_path.rsplit(".", 1)[0] + ".wav"

    cmd = [
        FFMPEG_PATH,
        "-i", video_path,
        "-vn",                # без видео
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "16000",       # 16kHz
        "-ac", "1",           # mono
        "-y",                 # перезаписать
        wav_path,
    ]

    logger.info(f"Extracting audio: {video_path} -> {wav_path}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        logger.error(f"ffmpeg error: {result.stderr}")
        # Видео без аудиодорожки — сигнализируем None, прочие ошибки поднимаем
        if "does not contain any stream" in result.stderr:
            logger.info("Video has no audio track")
            return None
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:200]}")

    logger.info(f"Audio extracted: {wav_path}")
    return wav_path


async def transcribe_audio(wav_path: str) -> str:
    """
    Транскрибирует аудио через Groq Whisper API.
    Возвращает распознанный текст.
    """
    logger.info(f"Transcribing: {wav_path}")

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        with open(wav_path, "rb") as audio_file:
            files = {
                "file": ("audio.wav", audio_file, "audio/wav"),
            }
            data = {
                "model": config.GROQ_MODEL,
                "language": "ru",
                "response_format": "json",
            }
            headers = {
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
            }

            response = await client.post(
                config.GROQ_API_URL,
                files=files,
                data=data,
                headers=headers,
            )

        if response.status_code != 200:
            logger.error(f"Groq API error: {response.status_code} {response.text}")
            raise RuntimeError(f"Groq API error: {response.status_code}")

        result = response.json()
        text = result.get("text", "").strip()

        logger.info(f"Transcription result ({len(text.split())} words): {text[:100]}...")
        return text


async def transcribe(video_path: str) -> str:
    """
    Полный пайплайн: извлечение аудио + транскрибация.
    Возвращает текст транскрибации.
    """
    # ffmpeg — sync, запускаем в отдельном потоке
    wav_path = await asyncio.to_thread(extract_audio, video_path)
    if wav_path is None:
        # Нет аудиодорожки — трактуем как пустую транскрипцию,
        # чтобы пайплайн единообразно сделал fallback на описание
        return ""
    try:
        text = await transcribe_audio(wav_path)
    finally:
        # Удаляем WAV после транскрибации
        try:
            os.remove(wav_path)
        except OSError:
            pass

    return text
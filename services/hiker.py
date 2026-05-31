"""Скачивание Instagram Reels и получение описания через HikerAPI"""

import logging
import tempfile
from pathlib import Path

import httpx

import config

logger = logging.getLogger(__name__)

TEMP_DIR = Path(tempfile.gettempdir()) / "recipe-bot"
API_BASE = "https://api.hikerapi.com"


def _ensure_temp_dir() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


async def _get_media_info(client: httpx.AsyncClient, url: str) -> dict:
    """Получает информацию о медиа по URL через HikerAPI v1."""
    resp = await client.get(
        f"{API_BASE}/v1/media/by/url",
        params={"url": url},
    )
    resp.raise_for_status()
    return resp.json()


async def _download_file(client: httpx.AsyncClient, url: str, filepath: Path) -> int:
    """Скачивает файл по URL, возвращает размер в байтах."""
    total = 0
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(filepath, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=8192):
                f.write(chunk)
                total += len(chunk)
    return total


async def download_reel(url: str, message_id: int) -> tuple[str, str | None]:
    """
    Скачивает Instagram Reel по URL через HikerAPI.
    Возвращает (путь_к_файлу, описание).

    Raises:
        RuntimeError: если не удалось получить информацию или скачать видео
    """
    _ensure_temp_dir()

    headers = {
        "x-access-key": config.HIKER_API_KEY,
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(30.0, connect=10.0),
    ) as client:
        # Получаем информацию о медиа
        logger.info(f"HikerAPI: requesting media info for {url}")
        data = await _get_media_info(client, url)

        # Извлекаем поля
        caption = data.get("caption_text", "") or None
        video_url = data.get("video_url", "")
        shortcode = data.get("code", "unknown")
        username = data.get("user", {}).get("username", "unknown")
        full_name = data.get("user", {}).get("full_name", "")

        logger.info(
            f"HikerAPI: got info — author: {full_name} (@{username}), "
            f"shortcode: {shortcode}, caption: {len(caption) if caption else 0} chars"
        )

        if not video_url:
            raise RuntimeError(
                f"HikerAPI: video_url не найден в ответе API. "
                f"Ключи: {list(data.keys())}"
            )

        # Скачиваем видео
        output_path = TEMP_DIR / f"{message_id}.mp4"
        logger.info(f"HikerAPI: downloading video to {output_path}")

        download_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        try:
            size = await _download_file(download_client, video_url, output_path)
        finally:
            await download_client.aclose()

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("HikerAPI: не удалось скачать видео")

        size_mb = size / 1024 / 1024
        logger.info(f"HikerAPI: download complete — {output_path} ({size_mb:.1f} MB)")

        return str(output_path), caption


def cleanup_file(filepath: str) -> None:
    """Удаляет временный файл"""
    import os

    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Cleaned up: {filepath}")
        # Также пробуем удалить .wav файл если есть
        wav_path = filepath.rsplit(".", 1)[0] + ".wav"
        if os.path.exists(wav_path):
            os.remove(wav_path)
            logger.info(f"Cleaned up: {wav_path}")
    except Exception as e:
        logger.warning(f"Cleanup failed for {filepath}: {e}")
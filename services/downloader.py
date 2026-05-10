"""Скачивание видео через yt-dlp + извлечение описания"""

import logging
import os
import tempfile
from pathlib import Path

import yt_dlp

import config
import services.instagram_auth as instagram_auth

logger = logging.getLogger(__name__)

TEMP_DIR = Path(tempfile.gettempdir()) / "recipe-bot"


def _ensure_temp_dir() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def download_video(url: str, message_id: int) -> tuple[str, str | None]:
    """
    Скачивает видео по ссылке и возвращает (путь_к_файлу, описание).

    Raises:
        ValueError: если видео слишком длинное
        RuntimeError: если не удалось скачать
    """
    _ensure_temp_dir()
    output_path = TEMP_DIR / f"{message_id}.mp4"

    ydl_opts = {
        "outtmpl": str(output_path),
        "format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    # Cookies для Instagram (обход rate-limit)
    is_instagram = "instagram.com" in url
    cookies_file = Path(config.INSTAGRAM_COOKIES_FILE)

    if is_instagram:
        # Авто-обновление cookies при необходимости
        try:
            instagram_auth.refresh_cookies_if_needed()
        except Exception as e:
            logger.warning(f"Failed to refresh Instagram cookies: {e}")

    if cookies_file.exists():
        ydl_opts["cookiefile"] = str(cookies_file)
        logger.info(f"Using cookies from: {cookies_file}")
    elif is_instagram:
        logger.warning(
            "Instagram cookies file not found. "
            "Some videos may be unavailable. "
            "See COOKIES_GUIDE.md for manual cookie export instructions."
        )

    def _do_download(opts: dict) -> tuple[str, str | None]:
        """Внутренняя функция скачивания с заданными опциями."""
        with yt_dlp.YoutubeDL(opts) as ydl:
            logger.info(f"Extracting info: {url}")
            info = ydl.extract_info(url, download=False)

            # Проверка длительности
            duration = info.get("duration")
            if duration and duration > config.MAX_VIDEO_DURATION_SEC:
                raise ValueError(
                    f"Видео слишком длинное ({int(duration)} сек, максимум {config.MAX_VIDEO_DURATION_SEC} сек)"
                )

            # Извлекаем описание
            caption = info.get("description") or info.get("caption") or None

            # Скачиваем видео
            logger.info(f"Downloading video: {url}")
            ydl.download([url])

            if not output_path.exists():
                raise RuntimeError("Не удалось скачать видео")

            logger.info(f"Video saved: {output_path}")
            return str(output_path), caption

    try:
        try:
            return _do_download(ydl_opts)
        except yt_dlp.utils.DownloadError as e:
            # Если скачали с cookies и упали — пробуем без cookies
            if "cookiefile" in ydl_opts:
                logger.warning(f"Download with cookies failed, retrying without cookies: {e}")
                fallback_opts = {k: v for k, v in ydl_opts.items() if k != "cookiefile"}
                try:
                    return _do_download(fallback_opts)
                except yt_dlp.utils.DownloadError:
                    pass  # пробросим оригинальную ошибку ниже
            raise

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"Download error: {e}")
        if "login required" in error_msg.lower() or "rate-limit" in error_msg.lower():
            raise RuntimeError(
                "Не удалось скачать видео: Instagram требует авторизацию. "
                "Экспортируйте cookies из браузера (см. COOKIES_GUIDE.md) "
                "и поместите в data/instagram_cookies.txt"
            ) from e
        raise RuntimeError(f"Не удалось скачать видео: {e}") from e


def cleanup_file(filepath: str) -> None:
    """Удаляет временный файл"""
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
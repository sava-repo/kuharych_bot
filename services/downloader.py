"""Скачивание видео через yt-dlp + извлечение описания"""

import logging
import tempfile
from pathlib import Path

import yt_dlp

import config

logger = logging.getLogger(__name__)

TEMP_DIR = Path(tempfile.gettempdir()) / "recipe-bot"


def _ensure_temp_dir() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _validate_cookies_file(filepath: Path) -> bool:
    """
    Проверяет, что cookie-файл валиден:
    - Существует и не пустой
    - Формат Netscape (первая строка содержит заголовок)
    - Содержит sessionid
    """
    if not filepath.exists() or filepath.stat().st_size == 0:
        return False

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        lines = content.strip().splitlines()

        if not lines:
            return False

        # Проверяем Netscape-заголовок
        first_line = lines[0].lower()
        if "netscape" not in first_line:
            logger.warning(
                "Cookies file is not in Netscape format. "
                "Expected header: '# Netscape HTTP Cookie File'"
            )
            return False

        # Проверяем наличие sessionid
        has_sessionid = any("sessionid" in line.lower() for line in lines)
        if not has_sessionid:
            logger.warning("Cookies file does not contain 'sessionid' cookie")
            return False

        return True

    except Exception as e:
        logger.warning(f"Failed to validate cookies file: {e}")
        return False


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

    # Cookies для Instagram
    is_instagram = "instagram.com" in url
    cookies_file = Path(config.INSTAGRAM_COOKIES_FILE)

    if is_instagram and cookies_file.exists():
        if _validate_cookies_file(cookies_file):
            ydl_opts["cookiefile"] = str(cookies_file)
            logger.info(f"Using cookies from: {cookies_file}")
        else:
            logger.warning(
                "Cookies file exists but is invalid. "
                "Export fresh cookies from browser — see COOKIES_GUIDE.md"
            )
    elif is_instagram:
        logger.warning(
            "Instagram cookies file not found. "
            "Some videos may be unavailable. "
            "See COOKIES_GUIDE.md for cookie export instructions."
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
        return _do_download(ydl_opts)
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"Download error: {e}")
        if is_instagram and (
            "login required" in error_msg.lower()
            or "rate-limit" in error_msg.lower()
            or "HTTP Error 403" in error_msg
        ):
            raise RuntimeError(
                "Не удалось скачать видео: Instagram требует авторизацию. "
                "Экспортируйте свежие cookies из браузера (см. COOKIES_GUIDE.md) "
                "и поместите в data/instagram_cookies.txt"
            ) from e
        raise RuntimeError(f"Не удалось скачать видео: {e}") from e


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
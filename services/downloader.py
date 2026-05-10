"""Скачивание видео через yt-dlp + извлечение описания (fallback: kkclip для Instagram)"""

import logging
import re
import tempfile
from pathlib import Path

import httpx
import yt_dlp

import config

logger = logging.getLogger(__name__)

TEMP_DIR = Path(tempfile.gettempdir()) / "recipe-bot"


def _ensure_temp_dir() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


# ── kkclip fallback для Instagram ──────────────────────────────────────

KKCLIP_UA = "TelegramBot (like TwitterBot)"
KKCLIP_TIMEOUT = 15
KKCLIP_DOWNLOAD_TIMEOUT = 120


def _build_kkclip_url(url: str) -> str:
    """Строит kkclip URL из Instagram URL."""
    match = re.search(r"instagram\.com/(p|reel|tv)/([^/?#]+)", url)
    if not match:
        raise ValueError(f"Не Instagram URL: {url}")
    content_type = match.group(1)  # p, reel, tv
    shortcode = match.group(2)
    return f"https://kkclip.com/{content_type}/{shortcode}/"


def _download_via_kkclip(url: str, output_path: Path) -> str:
    """
    Скачивает Instagram видео через kkclip.
    Возвращает путь к скачанному файлу.
    """
    kkclip_url = _build_kkclip_url(url)
    logger.info(f"Trying kkclip fallback: {kkclip_url}")

    # Шаг 1: получаем прямую ссылку (302 redirect)
    with httpx.Client(timeout=KKCLIP_TIMEOUT, follow_redirects=False) as client:
        resp = client.get(kkclip_url, headers={"User-Agent": KKCLIP_UA})

        if resp.status_code == 404:
            raise RuntimeError("kkclip: контент не найден (404). Возможно, пост удалён или приватный.")

        if resp.status_code != 302:
            raise RuntimeError(f"kkclip вернул статус {resp.status_code}, ожидается 302")

        direct_url = resp.headers.get("Location", "")
        if not direct_url:
            raise RuntimeError("kkclip не вернул ссылку в заголовке Location")

    if ".mp4" not in direct_url:
        raise RuntimeError("kkclip: контент не является видео")

    logger.info(f"kkclip direct URL: {direct_url[:100]}...")

    # Шаг 2: скачиваем файл по прямой ссылке
    with httpx.Client(timeout=KKCLIP_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        with client.stream("GET", direct_url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)

    if not output_path.exists():
        raise RuntimeError("kkclip: не удалось скачать видео")

    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info(f"kkclip download complete: {output_path} ({size_mb:.1f} MB)")
    return str(output_path)


# ── Основные функции ──────────────────────────────────────────────────


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

    # Шаг 1: пробуем yt-dlp
    try:
        return _do_download(ydl_opts)
    except ValueError:
        raise  # Видео слишком длинное — не fallback, пробрасываем как есть
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"yt-dlp download failed: {e}")

        # Шаг 2: fallback через kkclip (только для Instagram)
        if is_instagram:
            logger.info("Attempting kkclip fallback for Instagram...")
            try:
                video_path = _download_via_kkclip(url, output_path)
                return video_path, None  # kkclip не возвращает описание
            except Exception as kkclip_err:
                logger.error(f"kkclip fallback also failed: {kkclip_err}")
                raise RuntimeError(
                    f"Не удалось скачать видео (yt-dlp: {error_msg[:100]}; "
                    f"kkclip: {kkclip_err})"
                ) from e

        raise

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
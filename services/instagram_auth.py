"""Автоматическая авторизация Instagram и экспорт cookies для yt-dlp"""

import logging
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import instaloader

import config

logger = logging.getLogger(__name__)

# Cookies считаются свежими 6 часов
COOKIES_MAX_AGE_SEC = 6 * 60 * 60

_instaloader_instance: instaloader.Instaloader | None = None


def _ensure_data_dir() -> None:
    """Создаёт директорию data/ если её нет"""
    Path(config.INSTAGRAM_COOKIES_FILE).parent.mkdir(parents=True, exist_ok=True)


def _export_cookies_to_netscape(session_cookies, filepath: str) -> None:
    """
    Экспортирует cookies из requests.Session в Netscape формат для yt-dlp.
    """
    _ensure_data_dir()
    cookie_jar = MozillaCookieJar(filepath)

    for cookie in session_cookies:
        cookie_jar.set_cookie(cookie)

    cookie_jar.save(ignore_discard=True, ignore_expires=True)
    logger.info(f"Cookies exported to: {filepath}")


def login_and_save_cookies() -> bool:
    """
    Авторизуется в Instagram через instaloader и экспортирует cookies.
    Возвращает True если успешно, False если не удалось.
    """
    if not config.INSTAGRAM_USERNAME or not config.INSTAGRAM_PASSWORD:
        logger.warning("Instagram credentials not set, skipping auto-login")
        return False

    global _instaloader_instance

    try:
        L = instaloader.Instaloader(
            download_videos=False,
            download_pictures=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )

        logger.info(f"Logging in to Instagram as: {config.INSTAGRAM_USERNAME}")
        L.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)

        # Сохраняем сессию instaloader
        _ensure_data_dir()
        L.save_session_to_file(config.INSTAGRAM_SESSION_FILE)

        # Экспортируем cookies для yt-dlp
        _export_cookies_to_netscape(
            L._session.cookies,
            config.INSTAGRAM_COOKIES_FILE,
        )

        _instaloader_instance = L
        logger.info("Instagram login successful, cookies saved")
        return True

    except instaloader.exceptions.TwoFactorAuthRequiredException:
        logger.warning("Instagram requires 2FA — manual intervention needed")
        raise RuntimeError(
            "Instagram требует двухфакторную аутентификацию. "
            "Пожалуйста, войдите вручную через браузер и экспортируйте cookies, "
            "или отключите 2FA для аккаунта бота."
        )

    except instaloader.exceptions.BadCredentialsException:
        logger.error("Instagram bad credentials")
        raise RuntimeError("Неверные данные для входа в Instagram. Проверьте INSTAGRAM_USERNAME и INSTAGRAM_PASSWORD")

    except instaloader.exceptions.ConnectionException as e:
        logger.error(f"Instagram connection error: {e}")
        raise RuntimeError(f"Не удалось подключиться к Instagram: {e}")

    except Exception as e:
        logger.error(f"Instagram login error: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка авторизации Instagram: {e}")


def _load_existing_session() -> bool:
    """
    Загружает существующую сессию instaloader из файла.
    Возвращает True если удалось.
    """
    global _instaloader_instance

    if not config.INSTAGRAM_USERNAME:
        return False

    session_file = Path(config.INSTAGRAM_SESSION_FILE)
    if not session_file.exists():
        return False

    try:
        L = instaloader.Instaloader(
            download_videos=False,
            download_pictures=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )
        L.load_session_from_file(config.INSTAGRAM_USERNAME, config.INSTAGRAM_SESSION_FILE)

        _instaloader_instance = L
        logger.info("Instagram session loaded from file")
        return True

    except Exception as e:
        logger.warning(f"Failed to load Instagram session: {e}")
        return False


def _cookies_are_fresh() -> bool:
    """Проверяет, свежие ли cookies файла (моложе COOKIES_MAX_AGE_SEC)"""
    cookies_path = Path(config.INSTAGRAM_COOKIES_FILE)
    if not cookies_path.exists():
        return False

    mtime = cookies_path.stat().st_mtime
    age = time.time() - mtime
    is_fresh = age < COOKIES_MAX_AGE_SEC

    if not is_fresh:
        logger.info(f"Cookies are stale ({int(age / 3600)}h old), refreshing...")

    return is_fresh


def refresh_cookies_if_needed() -> bool:
    """
    Проверяет свежесть cookies и обновляет при необходимости.
    Возвращает True если cookies доступны (свежие или обновлённые).
    """
    # Если cookies свежие — ничего не делаем
    if _cookies_are_fresh():
        logger.debug("Cookies are fresh, no refresh needed")
        return True

    # Пробуем загрузить существующую сессию
    if _instaloader_instance is None:
        _load_existing_session()

    # Если сессия есть, пробуем обновить cookies из неё
    if _instaloader_instance is not None:
        try:
            # Проверяем что сессия живая
            profile = _instaloader_instance.get_profile(config.INSTAGRAM_USERNAME)
            if profile:
                _export_cookies_to_netscape(
                    _instaloader_instance._session.cookies,
                    config.INSTAGRAM_COOKIES_FILE,
                )
                logger.info("Cookies refreshed from existing session")
                return True
        except Exception as e:
            logger.warning(f"Session expired, re-login needed: {e}")

    # Полный re-login
    try:
        return login_and_save_cookies()
    except RuntimeError:
        return False


def init_instagram_auth() -> None:
    """
    Инициализация при старте бота.
    Пробует загрузить сессию или авторизоваться.
    """
    if not config.INSTAGRAM_USERNAME or not config.INSTAGRAM_PASSWORD:
        logger.info("Instagram credentials not set, cookies won't be auto-generated")
        return

    # Сначала пробуем загрузить сохранённую сессию
    if _load_existing_session() and _cookies_are_fresh():
        logger.info("Instagram session loaded, cookies are fresh")
        return

    # Если сессия есть но cookies устарели — обновляем
    if _instaloader_instance is not None:
        try:
            _export_cookies_to_netscape(
                _instaloader_instance._session.cookies,
                config.INSTAGRAM_COOKIES_FILE,
            )
            logger.info("Cookies refreshed from loaded session")
            return
        except Exception:
            pass

    # Полная авторизация
    try:
        login_and_save_cookies()
    except RuntimeError as e:
        logger.warning(f"Auto-login failed at startup: {e}")
        logger.warning("Bot will work without Instagram cookies. Manual cookies file can be used as fallback.")
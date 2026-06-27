"""Получение username-ов пользователей через Telegram Bot API (getChat).

Кэшируется на всю жизнь процесса Streamlit (@st.cache_resource):
опрашиваем Telegram один раз при первом открытии дашборда, дальше
значения берутся из памяти. Принудительно обновить — кнопка «🔄 Обновить».
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st

from .db import db_path, get_connection

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/getChat"
_TIMEOUT = 8  # секунд на один getChat
_MAX_WORKERS = 5  # консервативно ниже лимита Telegram (~30 req/сек)


def get_bot_token() -> str | None:
    """Возвращает bot_token из st.secrets или None (с warning при отсутствии)."""
    try:
        token = st.secrets["bot_token"]
    except (KeyError, FileNotFoundError, st.errors.StreamlitAPIException):
        token = ""
    if not token:
        st.warning(
            "⚠️ Не задан `bot_token` в `.streamlit/secrets.toml`. "
            "Колонка «Username» будет пустой. "
            "Добавь `bot_token = \"...\"` (значение из `.env` бота) и перезапусти дашборд."
        )
        return None
    return token


def _get_chat(token: str, user_id: int) -> dict:
    """Один вызов getChat. Возвращает result, либо {} (с ретраем на 429)."""
    url = _API_BASE.format(token=token) + "?" + urlencode({"chat_id": user_id})
    req = Request(url, headers={"User-Agent": "kuharych-dashboard/1.0"})

    for _ in range(2):  # один ретрай после 429 Too Many Requests
        try:
            with urlopen(req, timeout=_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("result", {}) if payload.get("ok") else {}
        except HTTPError as exc:
            if exc.code == 429:
                retry_after = 1
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                    retry_after = int(body.get("parameters", {}).get("retry_after", 1))
                except (ValueError, OSError):
                    pass
                time.sleep(min(max(retry_after, 1), 10))
                continue
            logger.debug("getChat HTTP %s for %s", exc.code, user_id)
            return {}
        except (URLError, TimeoutError, OSError) as exc:
            logger.debug("getChat network error for %s: %s", user_id, exc)
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.debug("getChat failed for %s: %s", user_id, exc)
            return {}
    return {}


def _format_display(chat: dict) -> str:
    """@username → иначе «Имя Фамилия» → иначе «—»."""
    username = chat.get("username")
    if username:
        return f"@{username}"
    name = " ".join(
        p for p in (chat.get("first_name", ""), chat.get("last_name", "")) if p
    ).strip()
    return name or "—"


def _fetch_all(token: str, user_ids: tuple[int, ...]) -> dict[int, str]:
    """Параллельно опрашивает getChat для списка user_id."""
    result: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_get_chat, token, uid): uid for uid in user_ids}
        for fut in as_completed(futures):
            uid = futures[fut]
            try:
                result[uid] = _format_display(fut.result())
            except Exception as exc:  # noqa: BLE001
                logger.debug("username resolve failed for %s: %s", uid, exc)
                result[uid] = "—"
    return result


@st.cache_resource(show_spinner="📡 Загружаю username-ы из Telegram…")
def _load_usernames(token: str, db_path_str: str) -> dict[int, str]:
    """Единоразовая загрузка всех username-ов (один раз за жизнь процесса)."""
    if not token:
        return {}
    conn = get_connection(db_path_str)
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    user_ids = tuple(r["user_id"] for r in rows)
    return _fetch_all(token, user_ids)


def get_usernames() -> dict[int, str]:
    """Возвращает {user_id: отображаемая строка} из кэша процесса."""
    token = get_bot_token()
    if not token:
        return {}
    return _load_usernames(token, str(db_path()))


def clear_usernames_cache() -> None:
    """Сбрасывает кэш username-ов (кнопка «🔄 Обновить»)."""
    _load_usernames.clear()

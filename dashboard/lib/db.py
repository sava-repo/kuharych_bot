"""Подключение к локальной SQLite и кэшированные запросы.

Все страницы дашборда используют эти функции, чтобы не дублировать логику
поиска файла БД и обработки ошибок.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB = DATA_DIR / "bot.db"


@st.cache_resource
def get_connection(db_path: str) -> sqlite3.Connection:
    """Возвращает подключение к SQLite с row_factory.

    Кэшируется на жизнь процесса; Streamlit пересоздаст при смене path.
    `check_same_thread=False` нужен, т.к. Streamlit выполняет скрипты в
    разных потоках, а подключение мы держим одно (read-only локальный файл).
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_path() -> Path:
    """Путь к БД: из secrets, иначе дефолтный dashboard/data/bot.db."""
    try:
        secrets = st.secrets.get("connections", {}).get("bot_db", {})
    except st.errors.StreamlitAPIException:
        secrets = {}

    url = secrets.get("url", "") if isinstance(secrets, dict) else ""
    if url.startswith("sqlite:///"):
        rel = url.removeprefix("sqlite:///")
        return Path(rel)
    return DEFAULT_DB


def check_db() -> bool:
    """Проверяет наличие файла БД. Если нет — показывает инструкцию."""
    path = db_path()
    if path.exists():
        return True
    st.error(
        f"🛑 Файл БД не найден: `{path}`\n\n"
        "Положи свежий дамп `bot.db` из Amvera в папку `dashboard/data/` "
        "или укажи путь в `.streamlit/secrets.toml`."
    )
    st.code(
        "# .streamlit/secrets.toml\n"
        "[connections.bot_db]\n"
        'url = "sqlite:///data/bot.db"\n',
        language="toml",
    )
    return False


@st.cache_data(ttl=60)
def run_query(_conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    """Выполняет SELECT и возвращает DataFrame. Кэшируется на 60 сек."""
    return pd.read_sql_query(sql, _conn, params=params)
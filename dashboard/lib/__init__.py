"""Общие утилиты дашборда: подключение к БД и выполнение запросов."""

from .db import check_db, db_path, get_connection, run_query

__all__ = ["check_db", "db_path", "get_connection", "run_query"]
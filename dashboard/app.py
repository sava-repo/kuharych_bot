"""Кулинарыч — локальный дашборд администратора.

Точка входа Streamlit-приложения. Подключается к локальному snapshot-у
SQLite (dashboard/data/bot.db) и рисует обзорную страницу. Дополнительные
страницы лежат в папке pages/ и подхватываются Streamlit автоматически.

Запуск:
    cd dashboard
    streamlit run app.py
"""

from __future__ import annotations

import sqlite3

import streamlit as st

from lib import check_db, db_path, get_connection, run_query

st.set_page_config(
    page_title="Кулинарыч · Дашборд",
    page_icon="🍳",
    layout="wide",
)

st.title("🍳 Кулинарыч — дашборд администратора")
st.caption("Локальный просмотрщик базы данных бота (snapshot из Amvera)")

if not check_db():
    st.stop()

conn: sqlite3.Connection = get_connection(str(db_path()))

# Показываем путь и размер файла
db_file = db_path()
size_kb = db_file.stat().st_size / 1024
st.caption(f"📁 Файл: `{db_file}` · {size_kb:.1f} КБ")

# ─── Быстрые метрики на главной ────────────────────────────────────────────

st.divider()
st.subheader("📊 Быстрый обзор")

try:
    users_count = run_query(conn, "SELECT COUNT(*) AS c FROM users").iloc[0, 0]
    groups_count = run_query(conn, "SELECT COUNT(*) AS c FROM groups").iloc[0, 0]
    recipes_count = run_query(conn, "SELECT COUNT(*) AS c FROM group_recipes").iloc[0, 0]
    ingredients_count = run_query(
        conn, "SELECT COUNT(*) AS c FROM recipe_ingredients"
    ).iloc[0, 0]
except sqlite3.Error as exc:
    st.error(f"Ошибка при чтении БД: {exc}")
    st.stop()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Пользователи", int(users_count))
m2.metric("Группы", int(groups_count))
m3.metric("Рецепты (записей)", int(recipes_count))
m4.metric("Ингредиенты (записей)", int(ingredients_count))

# ─── Навигационный блок ────────────────────────────────────────────────────

st.divider()
st.subheader("📑 Страницы")

st.markdown(
    """
    Используй боковое меню или ссылки ниже:

    - 📊 **Обзор** — распределения и топы
    - 👥 **Группы** — таблица групп и составы
    - 🍳 **Рецепты** — таблица рецептов и ингредиенты
    - 🔍 **Поиск** — свободный SQL-браузер
    """
)

st.info(
    "💡 **Как обновить данные**: выгрузи свежий `bot.db` из Amvera, "
    "положи в `dashboard/data/bot.db` и нажми **R** в браузере (или кнопку "
    "**Rerun**). Подключение пересоздастся автоматически.",
    icon="💡",
)
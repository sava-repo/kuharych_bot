"""🔍 Поиск — быстрый поиск и свободный SQL-браузер."""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from lib import check_db, db_path, get_connection, run_query

st.set_page_config(page_title="Поиск · Кулинарыч", page_icon="🔍", layout="wide")
st.title("🔍 Поиск")

if not check_db():
    st.stop()

conn: sqlite3.Connection = get_connection(str(db_path()))


# ─── Быстрый поиск ─────────────────────────────────────────────────────────

st.subheader("🔎 Быстрый поиск")

tab_text, tab_url, tab_slug = st.tabs(["По тексту", "По source URL", "По slug"])

with tab_text:
    text_query = st.text_input(
        "Поиск по названию, ингредиентам, шагам",
        key="ing_query",
        placeholder="например: тирамису",
    )
    if text_query.strip():
        result = run_query(
            conn,
            """
            SELECT r.category,
                   r.slug,
                   r.title,
                   (SELECT COUNT(DISTINCT group_id) FROM group_recipes gr
                      WHERE gr.category = r.category AND gr.slug = r.slug) AS groups_count
            FROM recipes r
            WHERE r.title LIKE ? OR r.content_md LIKE ?
            ORDER BY groups_count DESC, r.title
            """,
            (f"%{text_query.strip()}%", f"%{text_query.strip()}%"),
        )
        st.caption(f"Найдено рецептов: {len(result)}")
        st.dataframe(
            result.rename(
                columns={
                    "category": "Категория",
                    "slug": "Slug",
                    "title": "Название",
                    "groups_count": "В группах",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )

with tab_url:
    url_query = st.text_input(
        "Часть URL",
        key="url_query",
        placeholder="например: instagram.com/reel/ABC",
    )
    if url_query.strip():
        result = run_query(
            conn,
            """
            SELECT source_url, category, slug
            FROM source_index
            WHERE source_url LIKE ?
            ORDER BY source_url
            """,
            (f"%{url_query.strip()}%",),
        )
        st.caption(f"Найдено строк: {len(result)}")
        st.dataframe(
            result.rename(
                columns={
                    "source_url": "URL",
                    "category": "Категория",
                    "slug": "Slug",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )

with tab_slug:
    slug_query = st.text_input(
        "Часть slug",
        key="slug_query",
        placeholder="например: borshch",
    )
    if slug_query.strip():
        result = run_query(
            conn,
            """
            SELECT DISTINCT category, slug
            FROM group_recipes
            WHERE slug LIKE ?
            ORDER BY category, slug
            """,
            (f"%{slug_query.strip()}%",),
        )
        st.caption(f"Найдено строк: {len(result)}")
        st.dataframe(
            result.rename(columns={"category": "Категория", "slug": "Slug"}),
            hide_index=True,
            use_container_width=True,
        )


# ─── Свободный SQL ─────────────────────────────────────────────────────────

st.divider()
st.subheader("🛠 Свободный SQL")

st.caption(
    "Выполняем только **SELECT**. Скрипт не пытается парсить — "
    "просто проверяем, что запрос начинается с SELECT (case-insensitive)."
)

default_query = "SELECT * FROM users LIMIT 10"
sql = st.text_area(
    "SQL-запрос",
    value=default_query,
    height=140,
    key="free_sql",
)

run_btn = st.button("▶️ Выполнить", type="primary", use_container_width=False)

if run_btn:
    norm = sql.strip()
    if not norm:
        st.warning("Введи запрос")
    elif not norm.lower().startswith("select") and not norm.lower().startswith("with"):
        st.error("🛑 Допускаются только SELECT / WITH запросы")
    else:
        try:
            df: pd.DataFrame = pd.read_sql_query(norm, conn)
            st.success("✅ Выполнено: " + str(len(df)) + " строк")
            st.dataframe(df, use_container_width=True)
        except sqlite3.Error as exc:
            st.error("❌ Ошибка SQL: " + str(exc))


# ─── Подсказка по схеме ────────────────────────────────────────────────────

with st.expander("📖 Схема БД"):
    st.markdown(
        """
        | Таблица | Колонки |
        |---------|---------|
        | `users` | `user_id`, `active_group` |
        | `groups` | `group_id`, `name`, `owner_id`, `invite_code` |
        | `group_members` | `group_id`, `user_id` |
        | `group_recipes` | `group_id`, `category`, `slug` |
        | `source_index` | `source_url`, `category`, `slug` |
        | `recipes` | `category`, `slug`, `title`, `content_md`, `source`, `full_text_lemmas`, `created` |
        | `recipe_ingredients` | `category`, `slug`, `ingredient`, `ingredient_lemmas` |
        """
    )
    st.code(
        """
        -- Пример: топ групп с количеством рецептов
        SELECT g.name, COUNT(gr.slug) AS recipes
        FROM groups g
        LEFT JOIN group_recipes gr ON gr.group_id = g.group_id
        GROUP BY g.group_id
        ORDER BY recipes DESC
        LIMIT 20;
        """,
        language="sql",
    )
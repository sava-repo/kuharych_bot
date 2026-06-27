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
            SELECT r.recipe_id,
                   r.slug,
                   r.title,
                   (SELECT COUNT(DISTINCT group_id) FROM group_recipes gr
                      WHERE gr.recipe_id = r.recipe_id) AS groups_count
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
                    "recipe_id": "ID",
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
        "Часть reel ID или URL",
        key="url_query",
        placeholder="например: DVSuWNrjaLo",
    )
    if url_query.strip():
        result = run_query(
            conn,
            """
            SELECT ri.reel_id, r.recipe_id, r.slug, r.source
            FROM reel_index ri
            LEFT JOIN recipes r ON r.recipe_id = ri.recipe_id
            WHERE ri.reel_id LIKE ? OR r.source LIKE ?
            ORDER BY ri.reel_id
            """,
            (f"%{url_query.strip()}%", f"%{url_query.strip()}%"),
        )
        st.caption(f"Найдено строк: {len(result)}")
        st.dataframe(
            result.rename(
                columns={
                    "reel_id": "Reel ID",
                    "recipe_id": "ID",
                    "slug": "Slug",
                    "source": "URL",
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
            SELECT recipe_id, slug, title
            FROM recipes
            WHERE slug LIKE ?
            ORDER BY slug
            """,
            (f"%{slug_query.strip()}%",),
        )
        st.caption(f"Найдено строк: {len(result)}")
        st.dataframe(
            result.rename(
                columns={"recipe_id": "ID", "slug": "Slug", "title": "Название"}
            ),
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
        | `users` | `user_id`, `active_group`, `registered_at` |
        | `groups` | `group_id`, `name`, `owner_id`, `invite_code` |
        | `group_members` | `group_id`, `user_id` |
        | `group_categories` | `category_id`, `group_id`, `name`, `position`, `is_default` |
        | `group_recipes` | `group_id`, `recipe_id`, `category_id`, `added_at`, `added_by_user_id` |
        | `reel_index` | `reel_id`, `recipe_id` |
        | `recipes` | `recipe_id`, `slug`, `title`, `content_md`, `source`, `full_text_lemmas`, `created` |
        | `recipe_ingredients` | `recipe_id`, `ingredient`, `ingredient_lemmas` |
        """
    )
    st.code(
        """
        -- Пример: топ групп с количеством рецептов
        SELECT g.name, COUNT(gr.recipe_id) AS recipes
        FROM groups g
        LEFT JOIN group_recipes gr ON gr.group_id = g.group_id
        GROUP BY g.group_id
        ORDER BY recipes DESC
        LIMIT 20;
        """,
        language="sql",
    )
"""📊 Обзор — распределения и топы."""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from lib import check_db, db_path, get_connection, get_usernames, run_query

st.set_page_config(page_title="Обзор · Кулинарыч", page_icon="📊", layout="wide")
st.title("📊 Обзор")

if not check_db():
    st.stop()

conn: sqlite3.Connection = get_connection(str(db_path()))


# ─── Рецепты по категориям ─────────────────────────────────────────────────

st.subheader("📂 Рецепты по категориям")

try:
    by_category = run_query(
        conn,
        """
        SELECT gc.name AS category, COUNT(DISTINCT gr.recipe_id) AS recipes
        FROM group_recipes gr
        JOIN group_categories gc ON gc.category_id = gr.category_id
        GROUP BY gc.name
        ORDER BY recipes DESC
        """,
    )
except sqlite3.Error as exc:
    st.error(f"Ошибка: {exc}")
    st.stop()

if by_category.empty:
    st.info("В БД ещё нет рецептов.")
else:
    col1, col2 = st.columns([3, 2])
    with col1:
        fig = px.bar(
            by_category,
            x="category",
            y="recipes",
            text="recipes",
            color="category",
            labels={"category": "Категория", "recipes": "Рецептов"},
        )
        fig.update_layout(showlegend=False, height=380)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(
            by_category.rename(
                columns={"category": "Категория", "recipes": "Рецептов"}
            ),
            hide_index=True,
            use_container_width=True,
        )


# ─── Топ групп по рецептам ─────────────────────────────────────────────────

st.divider()
st.subheader("👥 Топ-10 групп по количеству рецептов")

top_groups = run_query(
    conn,
    """
    SELECT g.group_id,
           g.name,
           COUNT(gr.recipe_id) AS recipes
    FROM groups g
    LEFT JOIN group_recipes gr ON gr.group_id = g.group_id
    GROUP BY g.group_id
    ORDER BY recipes DESC
    LIMIT 10
    """,
)

if top_groups.empty:
    st.info("В БД ещё нет групп.")
else:
    fig2 = px.bar(
        top_groups,
        x="recipes",
        y="name",
        orientation="h",
        text="recipes",
        color="recipes",
        color_continuous_scale="Tealgrn",
        labels={"name": "Группа", "recipes": "Рецептов"},
    )
    fig2.update_layout(
        yaxis={"categoryorder": "total ascending"},
        height=max(300, 35 * len(top_groups)),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)


# ─── Топ ингредиентов ──────────────────────────────────────────────────────

st.divider()
st.subheader("🥕 Топ-15 ингредиентов")

top_ingredients = run_query(
    conn,
    """
    SELECT ingredient, COUNT(DISTINCT recipe_id) AS recipes
    FROM recipe_ingredients
    GROUP BY ingredient
    ORDER BY recipes DESC
    LIMIT 15
    """,
)

if top_ingredients.empty:
    st.info("В БД ещё нет ингредиентов.")
else:
    fig3 = px.bar(
        top_ingredients,
        x="recipes",
        y="ingredient",
        orientation="h",
        text="recipes",
        color="recipes",
        color_continuous_scale="Mint",
        labels={"ingredient": "Ингредиент", "recipes": "В рецептах"},
    )
    fig3.update_layout(
        yaxis={"categoryorder": "total ascending"},
        height=500,
        showlegend=False,
    )
    st.plotly_chart(fig3, use_container_width=True)


# ─── Активность пользователей ──────────────────────────────────────────────

st.divider()
st.subheader("👤 Пользователи по количеству групп")

users_groups = run_query(
    conn,
    """
    SELECT u.user_id,
           COUNT(gm.group_id) AS groups
    FROM users u
    LEFT JOIN group_members gm ON gm.user_id = u.user_id
    GROUP BY u.user_id
    ORDER BY groups DESC
    """,
)

usernames = get_usernames()

if users_groups.empty:
    st.info("В БД ещё нет пользователей.")
else:
    users_groups["username"] = users_groups["user_id"].map(usernames).fillna("—")
    st.dataframe(
        users_groups[["username", "user_id", "groups"]].rename(
            columns={
                "username": "Username",
                "user_id": "User ID",
                "groups": "Состоит в группах",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
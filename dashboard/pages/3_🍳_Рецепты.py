"""🍳 Рецепты — таблица и детали рецептов."""

from __future__ import annotations

import sqlite3

import streamlit as st

from lib import check_db, db_path, get_connection, run_query

st.set_page_config(page_title="Рецепты · Кулинарыч", page_icon="🍳", layout="wide")
st.title("🍳 Рецепты")

if not check_db():
    st.stop()

conn: sqlite3.Connection = get_connection(str(db_path()))


# ─── Таблица всех рецептов ─────────────────────────────────────────────────

st.subheader("📚 Все рецепты (по recipe_id)")

recipes_df = run_query(
    conn,
    """
    SELECT r.recipe_id,
           r.slug,
           r.title,
           COUNT(DISTINCT gr.group_id) AS groups_count,
           r.source
    FROM recipes r
    LEFT JOIN group_recipes gr ON gr.recipe_id = r.recipe_id
    GROUP BY r.recipe_id
    ORDER BY groups_count DESC, r.slug
    """,
)

if recipes_df.empty:
    st.info("В БД ещё нет рецептов.")
    st.stop()

st.dataframe(
    recipes_df.rename(
        columns={
            "recipe_id": "ID",
            "slug": "Slug",
            "title": "Название",
            "groups_count": "В группах",
            "source": "Источник",
        }
    ),
    hide_index=True,
    use_container_width=True,
)


# ─── Категории групп ───────────────────────────────────────────────────────

st.divider()
st.subheader("📂 Категории по группам")

cat_df = run_query(
    conn,
    """
    SELECT g.name AS group_name,
           gc.name AS category,
           gc.is_default,
           COUNT(gr.recipe_id) AS recipes
    FROM group_categories gc
    JOIN groups g ON g.group_id = gc.group_id
    LEFT JOIN group_recipes gr ON gr.category_id = gc.category_id
    GROUP BY gc.category_id
    ORDER BY g.name, gc.position
    """,
)

if cat_df.empty:
    st.info("В БД ещё нет категорий.")
else:
    st.dataframe(
        cat_df.rename(
            columns={
                "group_name": "Группа",
                "category": "Категория",
                "is_default": "По умолчанию",
                "recipes": "Рецептов",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


# ─── Детали выбранного рецепта ─────────────────────────────────────────────

st.divider()
st.subheader("🔍 Детали рецепта")

recipe_options = {
    f"{row['title'] or row['slug']} (#{row['recipe_id']})": row["recipe_id"]
    for _, row in recipes_df.iterrows()
}

selected_label = st.selectbox("Выбери рецепт", list(recipe_options.keys()))
selected_id = recipe_options[selected_label]

col_groups, col_ingredients = st.columns(2)

with col_groups:
    st.markdown("**В каких группах / категориях сохранён**")
    in_groups = run_query(
        conn,
        """
        SELECT g.name AS group_name,
               gc.name AS category
        FROM group_recipes gr
        JOIN groups g ON g.group_id = gr.group_id
        JOIN group_categories gc ON gc.category_id = gr.category_id
        WHERE gr.recipe_id = ?
        ORDER BY g.name
        """,
        (selected_id,),
    )
    st.dataframe(
        in_groups.rename(columns={"group_name": "Группа", "category": "Категория"}),
        hide_index=True,
        use_container_width=True,
    )

with col_ingredients:
    st.markdown("**Ингредиенты**")
    ingredients_df = run_query(
        conn,
        """
        SELECT ingredient
        FROM recipe_ingredients
        WHERE recipe_id = ?
        ORDER BY ingredient
        """,
        (selected_id,),
    )
    if ingredients_df.empty:
        st.caption("Ингредиенты не индексированы")
    else:
        st.dataframe(
            ingredients_df.rename(columns={"ingredient": "Ингредиент"}),
            hide_index=True,
            use_container_width=True,
        )


# ─── Source URL ────────────────────────────────────────────────────────────

source_row = run_query(
    conn,
    "SELECT source FROM recipes WHERE recipe_id = ?",
    (selected_id,),
)

st.divider()
if not source_row.empty and source_row.iloc[0, 0]:
    source_url = source_row.iloc[0, 0]
    st.markdown(f"**🔗 Источник:** {source_url}")
else:
    st.caption("🔗 Источник не зарегистрирован")

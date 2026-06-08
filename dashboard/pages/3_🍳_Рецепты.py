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

st.subheader("📚 Все рецепты (по category/slug)")

recipes_df = run_query(
    conn,
    """
    SELECT gr.category,
           gr.slug,
           r.title,
           COUNT(DISTINCT gr.group_id) AS groups_count,
           (SELECT source_url FROM source_index si
              WHERE si.category = gr.category AND si.slug = gr.slug) AS source
    FROM (
        SELECT DISTINCT category, slug, group_id FROM group_recipes
    ) gr
    LEFT JOIN recipes r ON r.category = gr.category AND r.slug = gr.slug
    GROUP BY gr.category, gr.slug
    ORDER BY groups_count DESC, gr.category, gr.slug
    """,
)

if recipes_df.empty:
    st.info("В БД ещё нет рецептов.")
    st.stop()

st.dataframe(
    recipes_df.rename(
        columns={
            "category": "Категория",
            "slug": "Slug",
            "title": "Название",
            "groups_count": "В группах",
            "source": "Источник",
        }
    ),
    hide_index=True,
    use_container_width=True,
)


# ─── Фильтр по категории ───────────────────────────────────────────────────

st.divider()
st.subheader("📂 По категории")

categories = sorted(recipes_df["category"].unique().tolist())
selected_cat = st.selectbox("Категория", categories)

cat_df = recipes_df[recipes_df["category"] == selected_cat].drop(columns=["category"])
st.dataframe(
    cat_df.rename(
        columns={
            "slug": "Slug",
            "title": "Название",
            "groups_count": "В группах",
            "source": "Источник",
        }
    ),
    hide_index=True,
    use_container_width=True,
)


# ─── Детали выбранного рецепта ─────────────────────────────────────────────

st.divider()
st.subheader("🔍 Детали рецепта")

recipe_options = {
    f"{row['category']} / {row['slug']}": (row["category"], row["slug"])
    for _, row in recipes_df.iterrows()
}

selected_label = st.selectbox("Выбери рецепт", list(recipe_options.keys()))
selected_cat, selected_slug = recipe_options[selected_label]

col_groups, col_ingredients = st.columns(2)

with col_groups:
    st.markdown("**В каких группах сохранён**")
    in_groups = run_query(
        conn,
        """
        SELECT g.group_id, g.name
        FROM group_recipes gr
        JOIN groups g ON g.group_id = gr.group_id
        WHERE gr.category = ? AND gr.slug = ?
        ORDER BY g.name
        """,
        (selected_cat, selected_slug),
    )
    st.dataframe(
        in_groups.rename(columns={"group_id": "ID", "name": "Группа"}),
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
        WHERE category = ? AND slug = ?
        ORDER BY ingredient
        """,
        (selected_cat, selected_slug),
    )
    recipe_title_row = run_query(
        conn,
        "SELECT title FROM recipes WHERE category = ? AND slug = ?",
        (selected_cat, selected_slug),
    )
    if not recipe_title_row.empty:
        st.caption(f"**Название:** {recipe_title_row.iloc[0, 0]}")
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
    "SELECT source_url FROM source_index WHERE category = ? AND slug = ?",
    (selected_cat, selected_slug),
)

st.divider()
if not source_row.empty:
    source_url = source_row.iloc[0, 0]
    st.markdown(f"**🔗 Источник:** {source_url}")
else:
    st.caption("🔗 Источник не зарегистрирован")
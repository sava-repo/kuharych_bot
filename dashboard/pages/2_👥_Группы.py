"""👥 Группы — список и детали групп."""

from __future__ import annotations

import sqlite3

import streamlit as st

from lib import check_db, clear_usernames_cache, db_path, get_connection, get_usernames, run_query

st.set_page_config(page_title="Группы · Кулинарыч", page_icon="👥", layout="wide")
st.title("👥 Группы")

if not check_db():
    st.stop()

conn: sqlite3.Connection = get_connection(str(db_path()))

# ─── Username-ы из Telegram (кэш на жизнь процесса) ────────────────────────
usernames = get_usernames()

if st.button("🔄 Обновить username-ы", help="Перезапросить username-ы через Telegram Bot API"):
    clear_usernames_cache()
    st.rerun()


# ─── Общая таблица групп ───────────────────────────────────────────────────

st.subheader("🗂 Все группы")

groups_df = run_query(
    conn,
    """
    SELECT g.group_id,
           g.name,
           g.owner_id,
           g.invite_code,
           (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.group_id) AS members,
           (SELECT COUNT(*) FROM group_recipes gr WHERE gr.group_id = g.group_id) AS recipes,
           CASE WHEN g.group_id LIKE 'pers_%' THEN 'Личная' ELSE 'Общая' END AS type
    FROM groups g
    ORDER BY recipes DESC, members DESC
    """,
)

if groups_df.empty:
    st.info("В БД ещё нет групп.")
    st.stop()

groups_df["owner_username"] = groups_df["owner_id"].map(usernames).fillna("—")

st.dataframe(
    groups_df[
        [
            "group_id",
            "name",
            "owner_id",
            "owner_username",
            "invite_code",
            "members",
            "recipes",
            "type",
        ]
    ].rename(
        columns={
            "group_id": "ID",
            "name": "Название",
            "owner_id": "Владелец (ID)",
            "owner_username": "Владелец",
            "invite_code": "Инвайт",
            "members": "Участников",
            "recipes": "Рецептов",
            "type": "Тип",
        }
    ),
    hide_index=True,
    use_container_width=True,
)


# ─── Детали выбранной группы ───────────────────────────────────────────────

st.divider()
st.subheader("🔍 Детали группы")

group_options = {
    f"{row['name']} ({row['group_id']})": row["group_id"]
    for _, row in groups_df.iterrows()
}

selected_label = st.selectbox("Выбери группу", list(group_options.keys()))
selected_group_id = group_options[selected_label]

col_members, col_recipes = st.columns(2)

with col_members:
    st.markdown("**Участники**")
    members_df = run_query(
        conn,
        """
        SELECT gm.user_id,
               CASE WHEN u.user_id IS NULL THEN 'нет в users' ELSE 'активен' END AS status
        FROM group_members gm
        LEFT JOIN users u ON u.user_id = gm.user_id
        WHERE gm.group_id = ?
        ORDER BY gm.user_id
        """,
        (selected_group_id,),
    )
    members_df["username"] = members_df["user_id"].map(usernames).fillna("—")
    st.dataframe(
        members_df[["user_id", "username", "status"]].rename(
            columns={
                "user_id": "User ID",
                "username": "Username",
                "status": "Статус",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )

with col_recipes:
    st.markdown("**Рецепты группы**")
    recipes_df = run_query(
        conn,
        """
        SELECT gr.category,
               gr.slug,
               r.title,
               r.source
        FROM group_recipes gr
        LEFT JOIN recipes r ON r.category = gr.category AND r.slug = gr.slug
        WHERE gr.group_id = ?
        ORDER BY gr.category, gr.slug
        """,
        (selected_group_id,),
    )
    st.dataframe(
        recipes_df.rename(
            columns={
                "category": "Категория",
                "slug": "Slug",
                "title": "Название",
                "source": "Источник",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


# ─── Распределение по типам ────────────────────────────────────────────────

st.divider()
st.subheader("📊 Распределение по типам")

type_counts = groups_df["type"].value_counts().reset_index()
type_counts.columns = ["Тип", "Групп"]

st.dataframe(type_counts, hide_index=True, use_container_width=True)
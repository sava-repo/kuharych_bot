"""Unit tests for delete confirmation flow in handlers/buttons.py"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import services.group_manager as gm
import services.cache as cache
from handlers.buttons import (
    handle_delete,
    handle_delete_confirm,
    handle_delete_cancel,
)


RECIPE_MD = """---
title: "Тирамису"
source: "ig"
---
# Тирамису
## Ингредиенты
- Маскарпоне 250г
## Способ приготовления
1. Взбить крем
"""


def _make_callback(data: str) -> MagicMock:
    """Создаёт фиктивный CallbackQuery с async-методами."""
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 123
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    return cb


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestDeleteConfirmation:
    """Шаг 1: показ диалога подтверждения"""

    @pytest.mark.asyncio
    async def test_handle_delete_shows_dialog_with_title(self):
        rk = cache.put({"recipe_id": 42, "group_id": "g1"})
        cb = _make_callback(f"del:{rk}")

        with patch.object(
            gm,
            "get_recipe",
            return_value={"title": "Тирамису", "content_md": RECIPE_MD, "source": "ig"},
        ):
            await handle_delete(cb)

        cb.answer.assert_awaited_once()
        cb.message.edit_text.assert_awaited_once()
        text = cb.message.edit_text.call_args.args[0]
        markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
        assert "Вы действительно хотите удалить рецепт «Тирамису»?" == text
        assert markup is not None

    @pytest.mark.asyncio
    async def test_handle_delete_falls_back_to_recipe_id_when_no_recipe(self):
        rk = cache.put({"recipe_id": 42, "group_id": "g1"})
        cb = _make_callback(f"del:{rk}")

        with patch.object(gm, "get_recipe", return_value=None):
            await handle_delete(cb)

        text = cb.message.edit_text.call_args.args[0]
        assert "#42" in text


class TestDeleteConfirm:
    """Шаг 2 (Да): реальное удаление"""

    @pytest.mark.asyncio
    async def test_confirm_removes_recipe(self):
        rk = cache.put({"recipe_id": 42, "group_id": "g1"})
        cb = _make_callback(f"delok:{rk}")

        with patch.object(gm, "remove_recipe_from_group", return_value=True) as m_remove, \
                patch.object(gm, "recipe_exists_in_any_group", return_value=False), \
                patch.object(gm, "delete_recipe") as m_delete:
            await handle_delete_confirm(cb)

        m_remove.assert_called_once_with("g1", 42)
        m_delete.assert_called_once_with(42)
        text = cb.message.edit_text.call_args.args[0]
        assert "удалён" in text

    @pytest.mark.asyncio
    async def test_confirm_keeps_recipe_when_in_other_group(self):
        rk = cache.put({"recipe_id": 42, "group_id": "g1"})
        cb = _make_callback(f"delok:{rk}")

        with patch.object(gm, "remove_recipe_from_group", return_value=True), \
                patch.object(gm, "recipe_exists_in_any_group", return_value=True), \
                patch.object(gm, "delete_recipe") as m_delete:
            await handle_delete_confirm(cb)

        m_delete.assert_not_called()


class TestDeleteCancel:
    """Шаг 2 (Нет): возврат к просмотру рецепта"""

    @pytest.mark.asyncio
    async def test_cancel_restores_recipe_view(self):
        rk = cache.put({"recipe_id": 42, "group_id": "g1"})
        cb = _make_callback(f"delcn:{rk}")

        with patch.object(
            gm,
            "get_recipe",
            return_value={"title": "Тирамису", "content_md": RECIPE_MD, "source": "ig"},
        ), patch.object(gm, "find_source_by_recipe_id", return_value=None), \
                patch.object(gm, "get_group_recipe_category", return_value=None):
            await handle_delete_cancel(cb)

        cb.answer.assert_awaited_once()
        cb.message.edit_text.assert_awaited_once()
        text = cb.message.edit_text.call_args.args[0]
        markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
        assert "Тирамису" in text
        assert markup is not None

    @pytest.mark.asyncio
    async def test_cancel_shows_error_when_recipe_gone(self):
        rk = cache.put({"recipe_id": 42, "group_id": "g1"})
        cb = _make_callback(f"delcn:{rk}")

        with patch.object(gm, "get_recipe", return_value=None):
            await handle_delete_cancel(cb)

        text = cb.message.edit_text.call_args.args[0]
        assert "не найден" in text

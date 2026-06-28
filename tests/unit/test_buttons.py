"""Unit tests for delete confirmation flow in handlers/buttons.py"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import services.group_manager as gm
from handlers.buttons import (
    handle_delete,
    handle_delete_confirm,
    handle_delete_cancel,
    handle_portions_change,
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

RECIPE_MD_PORTIONS = """---
title: "Борщ"
source: "ig"
portions: 4
calories: 1280
---
# Борщ
## Ингредиенты
- 400 г говядины
- по вкусу соль
## Способ приготовления
1. Варить
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


class TestDeleteConfirmation:
    """Шаг 1: показ диалога подтверждения"""

    @pytest.mark.asyncio
    async def test_handle_delete_shows_dialog_with_title(self):
        cb = _make_callback("del:42:g1")

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
        cb = _make_callback("del:42:g1")

        with patch.object(gm, "get_recipe", return_value=None):
            await handle_delete(cb)

        text = cb.message.edit_text.call_args.args[0]
        assert "#42" in text


class TestDeleteConfirm:
    """Шаг 2 (Да): реальное удаление"""

    @pytest.mark.asyncio
    async def test_confirm_removes_recipe(self):
        cb = _make_callback("delok:42:g1")

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
        cb = _make_callback("delok:42:g1")

        with patch.object(gm, "remove_recipe_from_group", return_value=True), \
                patch.object(gm, "recipe_exists_in_any_group", return_value=True), \
                patch.object(gm, "delete_recipe") as m_delete:
            await handle_delete_confirm(cb)

        m_delete.assert_not_called()


class TestDeleteCancel:
    """Шаг 2 (Нет): возврат к просмотру рецепта"""

    @pytest.mark.asyncio
    async def test_cancel_restores_recipe_view(self):
        cb = _make_callback("delcn:42:g1")

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
        cb = _make_callback("delcn:42:g1")

        with patch.object(gm, "get_recipe", return_value=None):
            await handle_delete_cancel(cb)

        text = cb.message.edit_text.call_args.args[0]
        assert "не найден" in text


def _button_texts(markup) -> list[str]:
    """Собирает тексты всех кнопок inline-клавиатуры."""
    texts = []
    for row in markup.inline_keyboard:
        for btn in row:
            texts.append(btn.text)
    return texts


def _button_callbacks(markup) -> list[str]:
    cbs = []
    for row in markup.inline_keyboard:
        for btn in row:
            cbs.append(btn.callback_data or "")
    return cbs


class TestPortionsChange:
    """Кнопка пересчёта числа порций (psc:)"""

    @pytest.mark.asyncio
    async def test_psc_scales_ingredients_and_shows_current(self):
        cb = _make_callback("psc:42:g1:6")

        with patch.object(
            gm, "get_recipe",
            return_value={"title": "Борщ", "content_md": RECIPE_MD_PORTIONS, "source": "ig"},
        ), patch.object(gm, "get_group_recipe_category", return_value=None), \
                patch.object(gm, "find_source_by_recipe_id", return_value=None):
            await handle_portions_change(cb)

        cb.answer.assert_awaited_once()
        text = cb.message.edit_text.call_args.args[0]
        markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
        # коэффициент 6/4 = 3/2 → 600 г говядины
        assert "600 г говядины" in text
        assert "по вкусу соль" in text
        # клавиатура: текущее 6 порций, кнопки на 5 и 7
        texts = _button_texts(markup)
        cbs = _button_callbacks(markup)
        assert "6 порций" in texts
        assert "psc:42:g1:5" in cbs
        assert "psc:42:g1:7" in cbs

    @pytest.mark.asyncio
    async def test_psc_clamps_target_to_max(self):
        cb = _make_callback("psc:42:g1:50")

        with patch.object(
            gm, "get_recipe",
            return_value={"title": "Борщ", "content_md": RECIPE_MD_PORTIONS, "source": "ig"},
        ), patch.object(gm, "get_group_recipe_category", return_value=None), \
                patch.object(gm, "find_source_by_recipe_id", return_value=None):
            await handle_portions_change(cb)

        markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
        texts = _button_texts(markup)
        # clamped до 20 → «20 порций», кнопки ➕ быть не должно
        assert "20 порций" in texts
        assert "➕" not in texts

    @pytest.mark.asyncio
    async def test_psc_malformed_callback_shows_alert(self):
        # некорректная структура (нет group_id/числа порций) → alert, без БД
        cb = _make_callback("psc:42:6")

        await handle_portions_change(cb)

        cb.answer.assert_awaited_once()
        cb.message.edit_text.assert_not_awaited()

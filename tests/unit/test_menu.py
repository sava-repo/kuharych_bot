"""Unit tests for handlers/menu.py — random recipe selection logic."""
from unittest.mock import MagicMock

import services.group_manager as gm
import services.rotation as rotation
from handlers import menu


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


def _recipe_data():
    return {"content_md": RECIPE_MD, "source": "ig"}


class TestPickRandomRecipe:
    """Поведение _pick_random_recipe: фильтрация орфанов и rotation."""

    def test_filters_orphans_and_uses_valid_total_for_rotation(self, monkeypatch):
        """Орфан (нет записи в recipes) отбрасывается; rotation.add получает
        валидный recipe_id и total = кол-во валидных."""
        def fake_get_recipe(recipe_id):
            return _recipe_data() if recipe_id == "valid" else None

        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category",
            lambda gid, cat_id: ["orphan", "valid"],
        )
        monkeypatch.setattr(menu.gm, "get_recipe", fake_get_recipe)
        monkeypatch.setattr(menu.gm, "find_source_by_recipe_id", lambda rid: None)
        monkeypatch.setattr(menu.rotation, "get_excluded", lambda uid, cat_id: [])

        added = []
        monkeypatch.setattr(
            menu.rotation, "add",
            lambda uid, cat_id, rid, total: added.append((rid, total)),
        )
        monkeypatch.setattr(
            menu.random, "choice",
            lambda seq: next(p for p in seq if p[0] == "valid"),
        )

        result = menu._pick_random_recipe(1, "g1", 7, "десерт")

        assert result is not None
        assert result["recipe"].title == "Тирамису"
        assert added == [("valid", 1)]  # орфан не в rotation, total=1

    def test_returns_none_when_only_orphans(self, monkeypatch):
        """Если в категории только осиротевшие recipe_id — None, rotation не трогается."""
        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category",
            lambda gid, cat_id: ["orphan1", "orphan2"],
        )
        monkeypatch.setattr(menu.gm, "get_recipe", lambda rid: None)

        added = []
        monkeypatch.setattr(menu.rotation, "add", lambda *a: added.append(a))

        assert menu._pick_random_recipe(1, "g1", 7, "десерт") is None
        assert added == []

    def test_returns_none_when_group_empty(self, monkeypatch):
        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category", lambda gid, cat_id: [],
        )
        assert menu._pick_random_recipe(1, "g1", 7, "десерт") is None

    def test_excludes_recently_shown_valid_recipes(self, monkeypatch):
        """rotation.get_excluded убирает recipe_id из кандидатов на выбор."""
        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category",
            lambda gid, cat_id: ["a", "b"],
        )
        monkeypatch.setattr(menu.gm, "get_recipe", lambda rid: _recipe_data())
        monkeypatch.setattr(menu.gm, "find_source_by_recipe_id", lambda rid: None)
        monkeypatch.setattr(menu.rotation, "get_excluded", lambda uid, cat_id: ["a"])
        monkeypatch.setattr(menu.rotation, "add", lambda *a: None)

        captured = {}
        monkeypatch.setattr(
            menu.random, "choice",
            lambda seq: (captured.__setitem__("seq", [p[0] for p in seq]) or seq[0]),
        )

        menu._pick_random_recipe(1, "g1", 7, "десерт")
        assert captured["seq"] == ["b"]

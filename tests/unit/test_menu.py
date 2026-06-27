"""Unit tests for handlers/menu.py — random recipe selection logic."""
from unittest.mock import MagicMock

import services.group_manager as gm
import services.rotation as rotation
from handlers import menu


RECIPE_MD = """---
title: "Тирамису"
category: "десерт"
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
        валидный slug и total = кол-во валидных."""
        def fake_get_recipe(category, slug):
            return _recipe_data() if slug == "valid" else None

        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category",
            lambda gid, cat: ["orphan", "valid"],
        )
        monkeypatch.setattr(menu.gm, "get_recipe", fake_get_recipe)
        monkeypatch.setattr(menu.gm, "find_source_by_slug", lambda c, s: None)
        monkeypatch.setattr(menu.rotation, "get_excluded", lambda uid, cat: [])

        added = []
        monkeypatch.setattr(
            menu.rotation, "add",
            lambda uid, cat, slug, total: added.append((slug, total)),
        )
        # заставляем random.choice выбрать валидную пару
        monkeypatch.setattr(
            menu.random, "choice",
            lambda seq: next(p for p in seq if p[0] == "valid"),
        )

        result = menu._pick_random_recipe(1, "g1", "десерт")

        assert result is not None
        assert result["recipe"].title == "Тирамису"
        assert added == [("valid", 1)]  # орфан не в rotation, total=1

    def test_returns_none_when_only_orphans(self, monkeypatch):
        """Если в категории только осиротевшие slug'и — None, rotation не трогается."""
        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category",
            lambda gid, cat: ["orphan1", "orphan2"],
        )
        monkeypatch.setattr(menu.gm, "get_recipe", lambda c, s: None)

        added = []
        monkeypatch.setattr(menu.rotation, "add", lambda *a: added.append(a))

        assert menu._pick_random_recipe(1, "g1", "десерт") is None
        assert added == []

    def test_returns_none_when_group_empty(self, monkeypatch):
        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category", lambda gid, cat: [],
        )
        assert menu._pick_random_recipe(1, "g1", "десерт") is None

    def test_excludes_recently_shown_valid_slugs(self, monkeypatch):
        """rotation.get_excluded убирает слаг из кандидатов на выбор."""
        monkeypatch.setattr(
            menu.gm, "get_group_recipes_by_category",
            lambda gid, cat: ["a", "b"],
        )
        monkeypatch.setattr(menu.gm, "get_recipe", lambda c, s: _recipe_data())
        monkeypatch.setattr(menu.gm, "find_source_by_slug", lambda c, s: None)
        monkeypatch.setattr(menu.rotation, "get_excluded", lambda uid, cat: ["a"])
        monkeypatch.setattr(menu.rotation, "add", lambda *a: None)

        captured = {}
        monkeypatch.setattr(
            menu.random, "choice",
            lambda seq: (captured.__setitem__("seq", [p[0] for p in seq]) or seq[0]),
        )

        menu._pick_random_recipe(1, "g1", "десерт")
        assert captured["seq"] == ["b"]

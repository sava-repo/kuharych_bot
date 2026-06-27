"""Dataclass для категории уровня группы"""

from dataclasses import dataclass


@dataclass
class Category:
    """Категория, принадлежащая конкретной группе."""
    category_id: int
    group_id: str
    name: str
    position: int = 0
    is_default: bool = False

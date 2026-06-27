"""Модели для пользователей и групп"""

from dataclasses import dataclass, field


@dataclass
class User:
    """Пользователь бота"""
    user_id: int
    active_group: str = ""  # ID текущей активной группы
    registered_at: str | None = None  # ISO-8601 дата регистрации


@dataclass
class Group:
    """Группа пользователей для совместного доступа к рецептам"""
    group_id: str           # Уникальный ID (pers_123 / grp_abc)
    name: str               # Название группы
    owner_id: int           # ID создателя группы
    members: list[int] = field(default_factory=list)
    invite_code: str | None = None  # Код для вступления

    @property
    def is_personal(self) -> bool:
        """Личная группа пользователя"""
        return self.group_id.startswith("pers_")
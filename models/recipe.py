"""Dataclass для рецепта"""

from dataclasses import dataclass, field


@dataclass
class Recipe:
    title: str
    ingredients: list[str]
    steps: list[str]
    category: str  # завтрак / основное блюдо / десерт
    source: str
    tags: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """URL-safe slug из названия блюда"""
        slug = self.title.lower().strip()
        slug = slug.replace(" ", "-")
        # Убираем лишние символы, оставляем буквы, цифры, дефисы
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        # Убираем двойные дефисы
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug.strip("-")

    def format_message(self) -> str:
        """Форматирование рецепта для отправки в чат"""
        ingredients_text = "\n".join(f"• {ing}" for ing in self.ingredients)
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(self.steps))

        return (
            f"🍳 {self.title}\n\n"
            f"📋 Ингредиенты:\n{ingredients_text}\n\n"
            f"👨‍🍳 Приготовление:\n{steps_text}\n\n"
            f"📂 Категория: {self.category}"
        )

    def to_markdown(self, created: str) -> str:
        """Форматирование рецепта в Markdown с YAML frontmatter для Gramax"""
        import json

        tags_str = json.dumps(self.tags, ensure_ascii=False)
        ingredients_text = "\n".join(f"- {ing}" for ing in self.ingredients)
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(self.steps))

        return (
            f"---\n"
            f'title: "{self.title}"\n'
            f'category: "{self.category}"\n'
            f'source: "{self.source}"\n'
            f'created: "{created}"\n'
            f"tags: {tags_str}\n"
            f"---\n\n"
            f"# {self.title}\n\n"
            f"## Ингредиенты\n{ingredients_text}\n\n"
            f"## Способ приготовления\n{steps_text}\n"
        )
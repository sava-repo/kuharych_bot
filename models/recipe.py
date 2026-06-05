"""Dataclass для рецепта"""

import json
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

    @classmethod
    def from_markdown(cls, md_content: str, category: str, source: str) -> "Recipe":
        """Парсит рецепт из Markdown (после загрузки из GitHub).

        Args:
            md_content: содержимое .md файла с YAML frontmatter
            category: категория рецепта
            source: URL источника

        Returns:
            Объект Recipe
        """
        lines = md_content.strip().split("\n")
        title = ""
        ingredients: list[str] = []
        steps: list[str] = []
        current_section: str | None = None

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                continue
            if stripped.startswith("title:"):
                title = stripped.replace("title:", "").strip().strip('"')
                continue
            if stripped.startswith(("category:", "source:", "created:", "tags:")):
                continue
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                continue
            if stripped.startswith("## Ингредиенты"):
                current_section = "ingredients"
                continue
            if stripped.startswith("## Способ приготовления"):
                current_section = "steps"
                continue
            if current_section == "ingredients" and stripped.startswith("- "):
                ingredients.append(stripped[2:])
            elif current_section == "steps" and stripped and stripped[0].isdigit() and "." in stripped:
                step_text = stripped.split(".", 1)[1].strip()
                if step_text:
                    steps.append(step_text)

        return cls(
            title=title or "Без названия",
            ingredients=ingredients,
            steps=steps,
            category=category,
            source=source,
        )

    @staticmethod
    def format_markdown_for_chat(md_content: str) -> str:
        """Форматирует Markdown контент (из GitHub) для отправки в чат.

        Убирает YAML frontmatter и заменяет заголовки на эмодзи-формат.
        """
        lines = md_content.strip().split("\n")

        # Пропускаем YAML frontmatter
        in_frontmatter = False
        content_lines: list[str] = []
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            content_lines.append(line)

        # Убираем пустые строки в начале
        while content_lines and not content_lines[0].strip():
            content_lines.pop(0)

        text = "\n".join(content_lines)

        # Заменяем Markdown заголовки на читаемый формат
        text = text.replace("## Ингредиенты", "📋 Ингредиенты:")
        text = text.replace("## Способ приготовления", "👨‍🍳 Приготовление:")
        text = text.replace("# ", "🍳 ")

        return text

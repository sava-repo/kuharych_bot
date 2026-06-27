"""Dataclass для рецепта.

Категория — transient-поле: заполняется только ответом LLM при парсинге и
используется для выбора category_id при добавлении в группу. В хранилище
категория рецепта не хранится (она является тегом членства в группе).
"""

import json
from dataclasses import dataclass, field


@dataclass
class Recipe:
    title: str
    ingredients: list[str]
    steps: list[str]
    source: str
    category: str = ""  # transient: suggestion LLM, не сохраняется в content_md
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

    def format_message(self, category_name: str | None = None) -> str:
        """Форматирование рецепта для отправки в чат.

        category_name: имя категории в активной группе (выводится отдельной
            строкой, если передано). Категория — контекст группы, а не рецепта.
        """
        ingredients_text = "\n".join(f"• {ing}" for ing in self.ingredients)
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(self.steps))

        msg = (
            f"🍳 {self.title}\n\n"
            f"📋 Ингредиенты:\n{ingredients_text}\n\n"
            f"👨‍🍳 Приготовление:\n{steps_text}"
        )
        if category_name:
            msg += f"\n\n📂 Категория: {category_name}"
        return msg

    def to_markdown(self, created: str) -> str:
        """Форматирование рецепта в Markdown с YAML frontmatter.

        Категория не записывается (она является тегом группы, а не атрибутом
        рецепта).
        """
        tags_str = json.dumps(self.tags, ensure_ascii=False)
        ingredients_text = "\n".join(f"- {ing}" for ing in self.ingredients)
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(self.steps))

        return (
            f"---\n"
            f'title: "{self.title}"\n'
            f'source: "{self.source}"\n'
            f'created: "{created}"\n'
            f"tags: {tags_str}\n"
            f"---\n\n"
            f"# {self.title}\n\n"
            f"## Ингредиенты\n{ingredients_text}\n\n"
            f"## Способ приготовления\n{steps_text}\n"
        )

    @classmethod
    def from_markdown(cls, md_content: str, source: str) -> "Recipe":
        """Парсит рецепт из Markdown (после загрузки из хранилища).

        Args:
            md_content: содержимое .md файла с YAML frontmatter
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
            # Категория в frontmatter игнорируется (не атрибут рецепта)
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
            category="",
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

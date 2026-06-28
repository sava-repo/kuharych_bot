"""Dataclass для рецепта.

Категория — transient-поле: заполняется только ответом LLM при парсинге и
используется для выбора category_id при добавлении в группу. В хранилище
категория рецепта не хранится (она является тегом членства в группе).
"""

import json
from dataclasses import dataclass, field
from fractions import Fraction

from services.ingredient_scaler import scale_ingredients


def _parse_frontmatter_int(line: str) -> int:
    """Парсит целое из строки frontmatter вида 'key: 42'; при не-числе возвращает 0."""
    try:
        return int(line.split(":", 1)[1].strip())
    except (ValueError, TypeError):
        return 0


@dataclass
class Recipe:
    title: str
    ingredients: list[str]
    steps: list[str]
    source: str
    category: str = ""  # transient: suggestion LLM, не сохраняется в content_md
    tags: list[str] = field(default_factory=list)
    # КБЖУ — тотальные значения на всё блюдо (LLM-оценка); 0 = отсутствует
    portions: int = 0
    calories: int = 0
    protein: int = 0
    fat: int = 0
    carbs: int = 0

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

    def format_message(
        self,
        category_name: str | None = None,
        *,
        portions_override: int | None = None,
    ) -> str:
        """Форматирование рецепта для отправки в чат.

        category_name: имя категории в активной группе (выводится отдельной
            строкой, если передано). Категория — контекст группы, а не рецепта.
        portions_override: выбранное пользователем число порций. При передаче
            значения, отличного от ``self.portions`` (и при ``self.portions > 0``),
            ингредиенты пересчитываются через ``factor = override/portions``.
            Способ приготовления и строка КБЖУ не меняются. Результат эфемерен
            (только в сообщении, без записи в БД).
        """
        if portions_override and portions_override != self.portions and self.portions > 0:
            factor = Fraction(portions_override, self.portions)
            ingredients = scale_ingredients(self.ingredients, factor)
        else:
            ingredients = self.ingredients

        ingredients_text = "\n".join(f"• {ing}" for ing in ingredients)
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(self.steps))

        msg = f"🍳 {self.title}\n\n"
        nutrition_line = self._nutrition_line()
        if nutrition_line:
            msg += f"{nutrition_line}\n\n"
        msg += (
            f"📋 Ингредиенты:\n{ingredients_text}\n\n"
            f"👨‍🍳 Приготовление:\n{steps_text}"
        )
        if category_name:
            msg += f"\n\n📂 Категория: {category_name}"
        return msg

    def _nutrition_line(self) -> str:
        """Строка КБЖУ на одну порцию или пустая строка, если данных нет.

        Выводится только при `calories > 0` и `portions > 0`. Значения на порцию
        рассчитываются как total // portions (целочисленно, округление вниз).
        """
        if self.calories <= 0 or self.portions <= 0:
            return ""
        cal = self.calories // self.portions
        prot = self.protein // self.portions
        fat = self.fat // self.portions
        carbs = self.carbs // self.portions
        portions_note = "на 1 порцию" if self.portions == 1 else f"1 порция из {self.portions}"
        return (
            f"≈{cal} ккал · Б {prot} / Ж {fat} / У {carbs}   ({portions_note})"
        )

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
            f"portions: {self.portions}\n"
            f"calories: {self.calories}\n"
            f"protein: {self.protein}\n"
            f"fat: {self.fat}\n"
            f"carbs: {self.carbs}\n"
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
        tags: list[str] = []
        current_section: str | None = None
        portions = calories = protein = fat = carbs = 0

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                continue
            if stripped.startswith("title:"):
                title = stripped.replace("title:", "").strip().strip('"')
                continue
            # КБЖУ из frontmatter (int, толерантно к не-числам/отсутствию)
            if stripped.startswith("portions:"):
                portions = _parse_frontmatter_int(stripped)
                continue
            if stripped.startswith("calories:"):
                calories = _parse_frontmatter_int(stripped)
                continue
            if stripped.startswith("protein:"):
                protein = _parse_frontmatter_int(stripped)
                continue
            if stripped.startswith("fat:"):
                fat = _parse_frontmatter_int(stripped)
                continue
            if stripped.startswith("carbs:"):
                carbs = _parse_frontmatter_int(stripped)
                continue
            # tags из frontmatter (JSON-массив)
            if stripped.startswith("tags:"):
                tags_json = stripped.split(":", 1)[1].strip()
                try:
                    parsed = json.loads(tags_json)
                    if isinstance(parsed, list):
                        tags = [str(t) for t in parsed]
                except (ValueError, TypeError):
                    tags = []
                continue
            # Прочие служебные ключи frontmatter игнорируются (категория — не атрибут рецепта)
            if stripped.startswith(("category:", "source:", "created:")):
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
            tags=tags,
            portions=portions,
            calories=calories,
            protein=protein,
            fat=fat,
            carbs=carbs,
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

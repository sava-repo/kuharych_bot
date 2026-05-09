"""CRUD операции с рецептами через GitHub Contents API"""

import base64
import logging
from datetime import date

import httpx

import config
from models.recipe import Recipe

logger = logging.getLogger(__name__)


def _api_url(path: str = "") -> str:
    """Строит URL для GitHub Contents API"""
    return f"{config.GITHUB_API_BASE}/repos/{config.GITHUB_REPO}/contents/{path}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


async def _ensure_category_dir(category: str) -> None:
    """Создаёт папку категории через .gitkeep если её нет"""
    gitkeep_path = f"receipts/{category}/.gitkeep"
    url = _api_url(gitkeep_path)

    async with httpx.AsyncClient(timeout=30) as client:
        # Проверяем существует ли уже
        resp = await client.get(url, headers=_headers())
        if resp.status_code == 200:
            return  # Уже существует

        # Создаём .gitkeep
        content_b64 = base64.b64encode(b"").decode()
        resp = await client.put(
            url,
            headers=_headers(),
            json={
                "message": f"Create category: {category}",
                "content": content_b64,
            },
        )
        if resp.status_code in (200, 201):
            logger.info(f"Created category dir: {category}")
        else:
            logger.warning(f"Failed to create category dir: {resp.status_code} {resp.text}")


async def check_duplicate(category: str, slug: str) -> dict | None:
    """
    Проверяет наличие файла с таким slug в категории.
    Возвращает данные файла если найден, иначе None.
    """
    url = _api_url(f"receipts/{category}/{slug}.md")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())

    if resp.status_code == 200:
        data = resp.json()
        return {
            "sha": data["sha"],
            "path": data["path"],
        }
    return None


async def save_recipe(recipe: Recipe) -> str:
    """
    Сохраняет рецепт как Markdown файл в GitHub.
    Возвращает путь к файлу.
    """
    category = recipe.category
    slug = recipe.slug

    await _ensure_category_dir(category)

    md_content = recipe.to_markdown(created=date.today().isoformat())
    content_b64 = base64.b64encode(md_content.encode("utf-8")).decode()

    filepath = f"receipts/{category}/{slug}.md"
    url = _api_url(filepath)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            url,
            headers=_headers(),
            json={
                "message": f"Add recipe: {recipe.title}",
                "content": content_b64,
            },
        )

    if resp.status_code not in (200, 201):
        logger.error(f"GitHub API save error: {resp.status_code} {resp.text}")
        raise RuntimeError(f"Ошибка сохранения в GitHub: {resp.status_code}")

    logger.info(f"Recipe saved: {filepath}")
    return filepath


async def overwrite_recipe(recipe: Recipe, sha: str) -> str:
    """
    Перезаписывает существующий рецепт (нужен SHA предыдущей версии).
    """
    category = recipe.category
    slug = recipe.slug

    md_content = recipe.to_markdown(created=date.today().isoformat())
    content_b64 = base64.b64encode(md_content.encode("utf-8")).decode()

    filepath = f"receipts/{category}/{slug}.md"
    url = _api_url(filepath)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            url,
            headers=_headers(),
            json={
                "message": f"Update recipe: {recipe.title}",
                "content": content_b64,
                "sha": sha,
            },
        )

    if resp.status_code not in (200, 201):
        logger.error(f"GitHub API overwrite error: {resp.status_code} {resp.text}")
        raise RuntimeError(f"Ошибка обновления в GitHub: {resp.status_code}")

    logger.info(f"Recipe overwritten: {filepath}")
    return filepath


async def save_recipe_as_new(recipe: Recipe, suffix: int = 2) -> str:
    """
    Сохраняет рецепт с новым slug (добавляет суффикс -2, -3 и т.д.)
    """
    base_slug = recipe.slug
    new_slug = f"{base_slug}-{suffix}"

    # Проверяем есть ли уже такой
    existing = await check_duplicate(recipe.category, new_slug)
    if existing:
        return await save_recipe_as_new(recipe, suffix + 1)

    # Создаём новый рецепт с обновлённым slug (меняем title для нового slug)
    original_title = recipe.title
    recipe.title = f"{original_title} ({suffix})"
    try:
        return await save_recipe(recipe)
    finally:
        recipe.title = original_title


async def delete_recipe(category: str, slug: str) -> None:
    """
    Удаляет рецепт из GitHub.
    """
    # Сначала получаем SHA
    url = _api_url(f"receipts/{category}/{slug}.md")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())

        if resp.status_code != 200:
            raise RuntimeError(f"Файл не найден: {resp.status_code}")

        sha = resp.json()["sha"]

        # Удаляем
        resp = await client.delete(
            url,
            headers=_headers(),
            json={
                "message": f"Delete recipe: {slug}",
                "sha": sha,
            },
        )

    if resp.status_code not in (200, 201):
        logger.error(f"GitHub API delete error: {resp.status_code} {resp.text}")
        raise RuntimeError(f"Ошибка удаления из GitHub: {resp.status_code}")

    logger.info(f"Recipe deleted: receipts/{category}/{slug}.md")


async def list_recipes_in_category(category: str) -> list[dict]:
    """
    Возвращает список рецептов в категории.
    Каждый элемент: {"name": "slug.md", "path": "receipts/category/slug.md"}
    """
    url = _api_url(f"receipts/{category}/")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())

    if resp.status_code == 404:
        return []

    if resp.status_code != 200:
        logger.error(f"GitHub API list error: {resp.status_code} {resp.text}")
        raise RuntimeError(f"Ошибка чтения категории: {resp.status_code}")

    files = resp.json()
    # Фильтруем только .md файлы, исключаем .gitkeep
    return [
        {"name": f["name"], "path": f["path"]}
        for f in files
        if f["name"].endswith(".md") and f["name"] != ".gitkeep"
    ]


async def get_recipe_content(category: str, filename: str) -> str:
    """
    Получает содержимое рецепта из GitHub.
    Возвращает декодированный Markdown.
    """
    url = _api_url(f"receipts/{category}/{filename}")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())

    if resp.status_code != 200:
        logger.error(f"GitHub API get error: {resp.status_code} {resp.text}")
        raise RuntimeError(f"Ошибка чтения рецепта: {resp.status_code}")

    data = resp.json()
    content_b64 = data["content"]
    return base64.b64decode(content_b64).decode("utf-8")


async def move_recipe(
    old_category: str, slug: str, new_category: str, recipe: Recipe
) -> str:
    """
    Перемещает рецепт в другую категорию (удаляет старый, создаёт в новой).
    """
    # Удаляем из старой категории
    await delete_recipe(old_category, slug)

    # Сохраняем в новой
    recipe.category = new_category
    return await save_recipe(recipe)
"""Common pytest fixtures for all tests"""
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import httpx


# Set default testing environment for unit tests
os.environ.setdefault("TESTING_ENV", "local")


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for unit tests"""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.get.return_value = MagicMock(
        status_code=200,
        text="mocked response",
        json=lambda: {"mocked": "data"}
    )
    return client


@pytest.fixture
def env_testing_local(monkeypatch):
    """Set TESTING_ENV to 'local'"""
    monkeypatch.setenv("TESTING_ENV", "local")


@pytest.fixture
def env_testing_server(monkeypatch):
    """Set TESTING_ENV to 'server' for integration tests"""
    monkeypatch.setenv("TESTING_ENV", "server")


@pytest.fixture
def sample_instagram_url():
    """Sample Instagram Reel URL for testing"""
    return "https://www.instagram.com/reel/C_ABC123DEF/"


@pytest.fixture
def sample_instagram_url_with_params():
    """Sample Instagram Reel URL with query parameters"""
    return "https://www.instagram.com/reel/C_ABC123DEF/?utm_source=ig_web_copy_link"


@pytest.fixture
def sample_non_instagram_url():
    """Sample non-Instagram URL for testing"""
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def sample_llm_recipe_response():
    """Sample LLM response for recipe parsing"""
    return """```json
{
  "title": "Паста Карбонара",
  "ingredients": ["Спагетти 400г", "Бекон 200г", "Яйца 4 шт", "Пармезан 100г"],
  "steps": [
    "Отварите спагетти до аль денте",
    "Обжарьте бекон до хруста",
    "Смешайте яйца с пармезаном",
    "Соедините все ингредиенты и подавайте"
  ],
  "category": "основное блюдо",
  "tags": ["итальянская кухня", "быстро", "ужин"]
}
```"""


@pytest.fixture
def sample_malformed_json_response():
    """Sample malformed JSON response from LLM"""
    return """```json
{
  "title": "Recipe"
  "ingredients": [...]
```"""
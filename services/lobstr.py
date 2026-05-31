"""Получение описания (caption) Instagram Reels через Lobstr.io API"""

import asyncio
import logging
from urllib.parse import urlparse, urlunparse

import httpx

import config

logger = logging.getLogger(__name__)

API_BASE = "https://api.lobstr.io/v1"
CRAWLER_SLUG = "instagram-reels-scraper"
RUN_TIMEOUT = 120  # секунд ожидания завершения run


def _headers() -> dict:
    return {"Authorization": f"Token {config.LOBSTR_API_KEY}"}


def _is_instagram_url(url: str) -> bool:
    return "instagram.com" in url


def _clean_url(url: str) -> str:
    """Убрать query-параметры из URL (igsh= и т.д.)."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query="", fragment=""))


async def _find_crawler_id(client: httpx.AsyncClient) -> str:
    """Найти ID краулера по slug."""
    resp = await client.get(f"{API_BASE}/crawlers", headers=_headers())
    resp.raise_for_status()
    for c in resp.json()["data"]:
        if c["slug"] == CRAWLER_SLUG:
            return c["id"]
    raise RuntimeError(f"Crawler '{CRAWLER_SLUG}' not found in Lobstr.io")


async def _get_or_create_squid(client: httpx.AsyncClient, crawler_id: str) -> str:
    """Найти существующий squid или создать новый."""
    resp = await client.get(
        f"{API_BASE}/squids",
        headers=_headers(),
        params={"limit": 50, "page": 1},
    )
    resp.raise_for_status()
    for s in resp.json().get("data", []):
        if s.get("crawler") == crawler_id:
            return s["id"]

    # Создаём новый squid
    resp = await client.post(
        f"{API_BASE}/squids",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"name": "reel-caption-grabber", "crawler": crawler_id},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def _ensure_squid_ready(client: httpx.AsyncClient, squid_id: str) -> None:
    """Убедиться, что squid готов к запуску."""
    resp = await client.get(f"{API_BASE}/squids/{squid_id}", headers=_headers())
    resp.raise_for_status()
    if resp.json().get("is_ready"):
        return
    resp = await client.post(
        f"{API_BASE}/squids/{squid_id}",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"params": {"skip_pinned_reels": True}},
    )
    resp.raise_for_status()


async def _add_task(client: httpx.AsyncClient, squid_id: str, reel_url: str) -> None:
    """Добавить URL Reel как задачу."""
    resp = await client.post(
        f"{API_BASE}/tasks",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"squid": squid_id, "tasks": [{"url": reel_url}]},
    )
    resp.raise_for_status()
    logger.info(f"Lobstr: _add_task response for {reel_url}: {resp.json()}")


async def _start_run(client: httpx.AsyncClient, squid_id: str) -> str:
    """Запустить выполнение задач. Возвращает run_id."""
    resp = await client.post(
        f"{API_BASE}/runs",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"squid": squid_id},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def _wait_for_run(client: httpx.AsyncClient, run_id: str) -> None:
    """Ждать завершения run."""
    terminal = {"done", "aborted", "error"}
    for _ in range(RUN_TIMEOUT // 5):
        resp = await client.get(f"{API_BASE}/runs/{run_id}", headers=_headers())
        resp.raise_for_status()
        run = resp.json()
        if run["status"] in terminal:
            if run["status"] != "done":
                raise RuntimeError(f"Lobstr run failed: {run.get('done_reason', run['status'])}")
            return
        await asyncio.sleep(5)
    raise TimeoutError(f"Lobstr run {run_id} didn't finish in {RUN_TIMEOUT}s")


async def _get_caption(client: httpx.AsyncClient, run_id: str, reel_url: str) -> str | None:
    """Получить caption из результатов конкретного run, отфильтровав по запрошенному URL."""
    resp = await client.get(
        f"{API_BASE}/results",
        headers=_headers(),
        params={"run": run_id, "limit": 10, "page": 1},
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    logger.info(f"Lobstr: _get_caption got {len(data)} results for run {run_id}, looking for {reel_url}")

    for row in data:
        result_url = row.get("url") or row.get("input_url") or ""
        if not result_url:
            logger.debug(f"Lobstr: skipping result with no url (row id={row.get('id', '?')})")
            continue
        # Сравниваем без query-параметров (наши URL тоже очищены)
        if _clean_url(result_url) != _clean_url(reel_url):
            logger.debug(f"Lobstr: skipping result with url={result_url} (mismatch)")
            continue
        caption = row.get("caption")
        if caption:
            logger.info(f"Lobstr: matched caption for url={result_url} ({len(caption)} chars)")
            return caption.strip()
        else:
            logger.debug(f"Lobstr: matched url={result_url} but caption is empty")

    logger.warning(f"Lobstr: no matching result found for {reel_url} among {len(data)} results")
    return None


async def _cleanup_squid(client: httpx.AsyncClient, squid_id: str) -> None:
    """Очистить squid после использования."""
    try:
        await client.post(
            f"{API_BASE}/squids/{squid_id}/empty",
            headers={**_headers(), "Content-Type": "application/json"},
        )
    except Exception as e:
        logger.warning(f"Lobstr squid cleanup failed: {e}")


async def get_reel_caption(url: str) -> str | None:
    """
    Получить caption Reel через Lobstr.io API.
    Возвращает описание или None, если не удалось.
    """
    if not config.LOBSTR_API_KEY:
        logger.debug("LOBSTR_API_KEY not set, skipping Lobstr caption")
        return None

    if not _is_instagram_url(url):
        return None

    logger.info(f"Lobstr: getting caption for {url}")

    async with httpx.AsyncClient(timeout=30) as client:
        squid_id: str | None = None
        try:
            crawler_id = await _find_crawler_id(client)
            squid_id = await _get_or_create_squid(client, crawler_id)
            await _ensure_squid_ready(client, squid_id)
            cleaned_url = _clean_url(url)
            await _add_task(client, squid_id, cleaned_url)
            run_id = await _start_run(client, squid_id)
            await _wait_for_run(client, run_id)
            caption = await _get_caption(client, run_id, cleaned_url)

            if caption:
                logger.info(f"Lobstr: got caption ({len(caption)} chars)")
            else:
                logger.info("Lobstr: caption is empty or missing")

            return caption

        except Exception as e:
            logger.warning(f"Lobstr caption failed: {e}")
            return None

        finally:
            if squid_id:
                await _cleanup_squid(client, squid_id)
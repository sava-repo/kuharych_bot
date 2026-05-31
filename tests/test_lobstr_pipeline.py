"""Тест пайплайна Lobstr.io: получение caption из Instagram Reels"""

import asyncio
import sys
import os
import json

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx

API_BASE = "https://api.lobstr.io/v1"
CRAWLER_SLUG = "instagram-reels-scraper"
REEL_URL = "https://www.instagram.com/reel/DYP0xYVt77D/"
RUN_TIMEOUT = 180


def headers():
    api_key = os.getenv("LOBSTR_API_KEY", "")
    if not api_key:
        print("❌ LOBSTR_API_KEY не задан в .env")
        sys.exit(1)
    return {"Authorization": f"Token {api_key}"}


async def step_verify_auth(client: httpx.AsyncClient):
    """Шаг 1: Проверка авторизации"""
    print("\n=== Шаг 1: Проверка авторизации ===")
    resp = await client.get(f"{API_BASE}/me", headers=headers())
    resp.raise_for_status()
    user = resp.json()
    print(f"✅ Авторизован как: {user.get('first_name', '')} {user.get('last_name', '')} ({user.get('email', '')})")
    return user


async def step_check_balance(client: httpx.AsyncClient):
    """Шаг 2: Проверка баланса"""
    print("\n=== Шаг 2: Проверка баланса ===")
    resp = await client.get(f"{API_BASE}/user/balance", headers=headers())
    resp.raise_for_status()
    balance = resp.json()
    available = balance.get("available", 0)
    consumed = balance.get("consumed", 0)
    remaining = available - consumed
    print(f"💰 План: {balance.get('name', 'N/A')}")
    print(f"   Всего кредитов: {available}")
    print(f"   Потрачено: {consumed}")
    print(f"   Остаток: {remaining}")
    if remaining <= 0:
        print("⚠️  Нет кредитов!")
    return balance


async def step_find_crawler(client: httpx.AsyncClient):
    """Шаг 3: Найти crawler instagram-reels-scraper"""
    print(f"\n=== Шаг 3: Поиск crawler '{CRAWLER_SLUG}' ===")
    resp = await client.get(f"{API_BASE}/crawlers", headers=headers())
    resp.raise_for_status()
    data = resp.json()

    # Выведем все доступные Instagram-кравлеры
    print(f"   Всего краулеров: {data['total_results']}")
    insta_crawlers = [c for c in data["data"] if "instagram" in c.get("slug", "").lower()]
    print(f"   Instagram-краулеры:")
    for c in insta_crawlers:
        print(f"     - {c['slug']} (id: {c['id']}, credits/row: {c.get('credits_per_row')}, account required: {c.get('account') is not None})")

    for c in data["data"]:
        if c["slug"] == CRAWLER_SLUG:
            print(f"✅ Найден: {c['name']} (id: {c['id']})")
            print(f"   Требует аккаунт: {c.get('account') is not None}")
            print(f"   Доступен: {c.get('is_available')}")
            print(f"   Стоимость за строку: {c.get('credits_per_row')}")
            return c["id"], c

    print(f"❌ Crawler '{CRAWLER_SLUG}' не найден!")
    print("   Попробуем найти подходящий...")
    # Попробуем другие слаги
    for c in data["data"]:
        if "reel" in c.get("slug", "").lower() and "instagram" in c.get("slug", "").lower():
            print(f"   Альтернатива: {c['slug']} (id: {c['id']})")
    return None, None


async def step_create_squid(client: httpx.AsyncClient, crawler_id: str):
    """Шаг 4: Создать squid"""
    print(f"\n=== Шаг 4: Создание squid ===")
    payload = {
        "crawler": crawler_id,
        "name": "Test Reel Pipeline",
    }
    resp = await client.post(
        f"{API_BASE}/squids",
        headers={**headers(), "Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    squid = resp.json()
    print(f"✅ Squid создан: {squid['id']} (name: {squid['name']})")
    return squid["id"], squid


async def step_add_task(client: httpx.AsyncClient, squid_id: str, url: str):
    """Шаг 5: Добавить задачу"""
    print(f"\n=== Шаг 5: Добавление задачи ===")
    print(f"   URL: {url}")
    payload = {
        "squid": squid_id,
        "tasks": [{"url": url}],
    }
    resp = await client.post(
        f"{API_BASE}/tasks",
        headers={**headers(), "Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"✅ Добавлено задач: {len(data.get('tasks', []))}")
    print(f"   Дубликатов пропущено: {data.get('duplicated_count', 0)}")
    if data.get("tasks"):
        print(f"   Task ID: {data['tasks'][0]['id']}")
    return data


async def step_start_run(client: httpx.AsyncClient, squid_id: str):
    """Шаг 6: Запустить run"""
    print(f"\n=== Шаг 6: Запуск run ===")
    payload = {"squid": squid_id}
    resp = await client.post(
        f"{API_BASE}/runs",
        headers={**headers(), "Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    run = resp.json()
    print(f"✅ Run запущен: {run['id']} (status: {run['status']})")
    return run["id"], run


async def step_poll_run(client: httpx.AsyncClient, run_id: str):
    """Шаг 7: Поллить статус run"""
    print(f"\n=== Шаг 7: Ожидание завершения run (timeout: {RUN_TIMEOUT}s) ===")
    terminal = {"done", "aborted", "error"}
    elapsed = 0
    interval = 5

    while elapsed < RUN_TIMEOUT:
        resp = await client.get(f"{API_BASE}/runs/{run_id}", headers=headers())
        resp.raise_for_status()
        run = resp.json()
        status = run["status"]
        results = run.get("total_results", 0)

        print(f"   [{elapsed:3d}s] Status: {status} | Results: {results}")

        if status in terminal:
            print(f"\n✅ Run завершён: {status}")
            print(f"   Done reason: {run.get('done_reason')}")
            print(f"   Total results: {results}")
            print(f"   Credits used: {run.get('credit_used', 0)}")
            print(f"   Duration: {run.get('duration')}")
            return run

        await asyncio.sleep(interval)
        elapsed += interval

    print(f"⚠️  Таймаут ({RUN_TIMEOUT}s)!")
    return run


async def step_get_results(client: httpx.AsyncClient, squid_id: str):
    """Шаг 8: Получить результаты"""
    print(f"\n=== Шаг 8: Получение результатов ===")
    resp = await client.get(
        f"{API_BASE}/results",
        headers=headers(),
        params={"squid": squid_id, "limit": 10, "page": 1},
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"   Total results: {data.get('total_results', 0)}")

    if data.get("data"):
        print(f"\n📝 Результаты:")
        for i, row in enumerate(data["data"]):
            print(f"\n--- Результат #{i+1} ---")
            # Выводим все поля результата
            for key, value in row.items():
                if key not in ("id", "object", "squid", "run", "scraping_time"):
                    val_str = str(value)
                    if len(val_str) > 200:
                        val_str = val_str[:200] + "..."
                    print(f"  {key}: {val_str}")
    else:
        print("   Нет результатов")

    return data


async def step_cleanup_squid(client: httpx.AsyncClient, squid_id: str):
    """Очистка: удалить squid"""
    print(f"\n=== Очистка: удаление squid {squid_id} ===")
    resp = await client.delete(
        f"{API_BASE}/squids/{squid_id}",
        headers=headers(),
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Squid удалён: {data.get('deleted', False)}")
    else:
        print(f"⚠️  Не удалось удалить squid: {resp.status_code}")


async def main():
    print("=" * 60)
    print("🧪 Тест пайплайна Lobstr.io + Instagram Reels")
    print("=" * 60)

    squid_id = None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Шаг 1: Авторизация
            await step_verify_auth(client)

            # Шаг 2: Баланс
            await step_check_balance(client)

            # Шаг 3: Найти crawler
            crawler_id, crawler_info = await step_find_crawler(client)
            if not crawler_id:
                print("\n❌ Не удалось найти подходящий crawler. Тест прерван.")
                return

            # Проверяем наличие аккаунта
            if crawler_info.get("account"):
                print(f"\n⚠️  ВНИМАНИЕ: Этот crawler требует Instagram аккаунт!")
                print(f"   Тип аккаунта: {crawler_info['account'].get('type')}")
                print(f"   Cookies: {[c['name'] for c in crawler_info['account'].get('cookies', [])]}")

                # Проверяем есть ли привязанные аккаунты
                acc_resp = await client.get(f"{API_BASE}/accounts", headers=headers())
                acc_resp.raise_for_status()
                accounts = acc_resp.json()
                insta_accounts = [a for a in accounts.get("data", []) if "instagram" in a.get("type", "").lower()]
                if insta_accounts:
                    print(f"   Найдено Instagram-аккаунтов: {len(insta_accounts)}")
                    for a in insta_accounts:
                        print(f"     - {a['username']} (status: {a['status_code_info']})")
                else:
                    print(f"   ❌ Нет привязанных Instagram-аккаунтов!")

            # Шаг 4: Создать squid
            squid_id, squid_info = await step_create_squid(client, crawler_id)

            # Шаг 5: Добавить задачу
            await step_add_task(client, squid_id, REEL_URL)

            # Шаг 6: Запустить run
            run_id, run_info = await step_start_run(client, squid_id)

            # Шаг 7: Поллить
            run_result = await step_poll_run(client, run_id)

            # Шаг 8: Получить результаты
            results = await step_get_results(client, squid_id)

            # Итог
            print("\n" + "=" * 60)
            if results.get("data"):
                print("✅ ТЕСТ ПРОЙДЕН — данные получены")
                # Попробуем найти caption
                for row in results["data"]:
                    caption = row.get("caption") or row.get("description") or row.get("text") or row.get("content")
                    if caption:
                        print(f"\n📋 Caption рилса:\n{caption}")
                        break
            else:
                print("⚠️  ТЕСТ ЗАВЕРШЁН — результатов нет")
                print(f"   Статус run: {run_result.get('status')}")
                print(f"   Причина: {run_result.get('done_reason')}")
                if run_result.get('done_reason_desc'):
                    print(f"   Описание: {run_result['done_reason_desc']}")
            print("=" * 60)

    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP ошибка: {e.response.status_code}")
        print(f"   URL: {e.request.url}")
        try:
            print(f"   Response: {json.dumps(e.response.json(), ensure_ascii=False, indent=2)}")
        except Exception:
            print(f"   Response: {e.response.text}")
    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
    finally:
        # Очистка
        if squid_id:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await step_cleanup_squid(client, squid_id)


if __name__ == "__main__":
    asyncio.run(main())
"""Точка входа для бэкфилла КБЖУ существующих рецептов.

Запуск:
    python -m services.nutrition_backfill
    python -m services.nutrition_backfill --dry-run
    python -m services.nutrition_backfill --limit 10
"""

import argparse
import asyncio
import logging

import config

from services.nutrition import backfill_all


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Бэкфилл КБЖУ для существующих рецептов"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только отобрать кандидатов и прогнать LLM без записи в БД",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Максимум обработанных рецептов (для пробы)",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = _parse_args()

    report = asyncio.run(backfill_all(dry_run=args.dry_run, limit=args.limit))

    mode = "[dry-run] " if args.dry_run else ""
    print(f"{mode}{report}")


if __name__ == "__main__":
    main()

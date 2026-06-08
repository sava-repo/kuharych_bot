"""Точка входа: запуск Telegram-бота"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from handlers import link, buttons, menu, groups

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set in .env")
        sys.exit(1)

    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(groups.router)
    dp.include_router(menu.router)
    dp.include_router(buttons.router)
    dp.include_router(link.router)

    logger.info("Bot starting (long polling)...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())

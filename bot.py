"""Точка входа: запуск Telegram-бота"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from handlers import link, buttons, menu, groups, testing
 +++++++ REPLACE

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

    # Регистрируем роутеры
    dp.include_router(groups.router)  # Группы (FSM states)
    dp.include_router(menu.router)    # Menu должно быть до link, чтобы перехватить кнопки
    dp.include_router(buttons.router) # Callback buttons
    dp.include_router(link.router)    # Обработка ссылок /start /help
    dp.include_router(testing.router) # Testing commands (/run_tests)
 +++++++ REPLACE

    logger.info("Bot starting (long polling)...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
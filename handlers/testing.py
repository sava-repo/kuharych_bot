"""Admin handler for running automated tests"""
import asyncio
import logging
import os

from aiogram import Router, F
from aiogram.types import Message
from aiogram.types import FSInputFile

import config
import services.test_runner as test_runner

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.text.startswith("/run_tests"))
async def handle_run_tests(message: Message) -> None:
    """
    Запускает автоматические тесты бэкенда.
    
    Формат: /run_tests [тип_тестов]
    
    Доступные типы:
    - (без аргумента): все тесты
    - unit: только unit тесты
    - lobstr: интеграционные тесты Lobstr API
    - pipeline: end-to-end пайплайн (Lobstr + Parser)
    - transcriber: тесты транскрибации Groq
    
    Только для администраторов (ADMIN_IDS).
    """
    user_id = message.from_user.id
    
    # Проверка админских прав
    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет прав для запуска тестов")
        return
    
    # Парсинг аргументов
    args = message.text.split()
    test_type = None
    
    if len(args) > 1:
        test_type = args[1].lower()
        
        # Валидация типа тестов
        valid_types = ["unit", "lobstr", "pipeline", "transcriber"]
        if test_type not in valid_types:
            await message.answer(
                f"❌ Неизвестный тип тестов: {test_type}\n\n"
                f"Доступные типы:\n"
                f"  /run_tests - все тесты\n"
                f"  /run_tests unit - только unit тесты\n"
                f"  /run_tests lobstr - тесты Lobstr API\n"
                f"  /run_tests pipeline - end-to-end пайплайн\n"
                f"  /run_tests transcriber - тесты транскрибации"
            )
            return
    
    # Отправляем подтверждение
    test_type_str = test_type if test_type else "все тесты"
    await message.answer(f"🧪 Запускаю {test_type_str}, подождите...\n\n⏱️ Это может занять несколько минут...")
    
    try:
        # Запускаем тесты в отдельном потоке (subprocess — синхронный)
        result, log_file_path = await asyncio.to_thread(
            test_runner.run_pytest,
            test_type=test_type,
            env="server",
            timeout=300,  # 5 минут
        )
        
        # Формируем сообщение с результатами
        summary = test_runner.format_test_summary(result)
        
        # Добавляем информацию о типе тестов
        test_type_info = f"\n📝 Тип тестов: {test_type if test_type else 'все тесты'}"
        summary += test_type_info
        
        # Отправляем сообщение с результатами
        await message.answer(summary, parse_mode="Markdown")
        
        # Если есть лог-файл, отправляем его
        if log_file_path and os.path.exists(log_file_path):
            try:
                log_file = FSInputFile(log_file_path)
                await message.answer_document(
                    log_file,
                    caption="📄 Полный лог выполнения тестов"
                )
                logger.info(f"Log file sent: {log_file_path}")
            except Exception as e:
                logger.error(f"Failed to send log file: {e}")
                await message.answer(
                    f"⚠️ Не удалось отправить файл с логами: {e}"
                )
        else:
            logger.warning("No log file generated or file doesn't exist")
        
        # Если тесты не прошли, добавляем детализацию
        if not result.success:
            if result.failed > 0:
                await message.answer(f"❌ Провалено тестов: {result.failed}")
            if result.errors > 0:
                await message.answer(f"⚠️ Ошибок в тестах: {result.errors}")
                
            # Показываем последние несколько строк из output для отладки
            if result.output:
                last_lines = result.output.split("\n")[-10:]
                debug_info = "\n".join(last_lines)
                await message.answer(
                    f"🔍 *Последние строки вывода:*\n```\n{debug_info}\n```",
                    parse_mode="Markdown"
                )
        
    except ValueError as e:
        # Ошибка валидации типа тестов (дубликат проверки, но для надежности)
        await message.answer(f"❌ Ошибка: {e}")
        
    except Exception as e:
        logger.error(f"Unexpected error running tests: {e}", exc_info=True)
        await message.answer(
            f"❌ Неизвестная ошибка при запуске тестов: {e}\n\n"
            f"Проверьте логи бота для деталей."
        )
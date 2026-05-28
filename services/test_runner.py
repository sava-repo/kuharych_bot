"""Service for running pytest tests via subprocess"""
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of pytest execution"""
    passed: int
    failed: int
    skipped: int
    errors: int
    duration: float
    output: str
    error_output: str
    success: bool
    timestamp: str


def run_pytest(
    test_type: Optional[str] = None,
    env: str = "server",
    timeout: int = 300,
) -> tuple[TestResult, Optional[str]]:
    """
    Запускает pytest в subprocess и возвращает результаты.
    
    Args:
        test_type: Тип тестов для запуска (lobstr, pipeline, transcriber, или None для всех)
        env: Окружение (local или server)
        timeout: Таймаут выполнения в секундах (по умолчанию 5 минут)
    
    Returns:
        Кортеж (TestResult, путь_к_файлу_с_логами)
    
    Raises:
        TimeoutError: Если тесты не завершились за указанное время
        RuntimeError: Если не удалось запустить pytest
    """
    # Базовая команда pytest
    cmd = ["python", "-m", "pytest", "-v"]
    
    # Фильтрация по типу тестов
    if test_type:
        test_paths = {
            "lobstr": "tests/integration/test_lobstr_live.py",
            "pipeline": "tests/integration/test_pipeline.py",
            "transcriber": "tests/integration/test_transcriber_live.py",
            "unit": "tests/unit/",
        }
        
        if test_type in test_paths:
            cmd.append(test_paths[test_type])
        else:
            raise ValueError(
                f"Неизвестный тип тестов: {test_type}. "
                f"Доступные: {', '.join(test_paths.keys())}"
            )
    else:
        # По умолчанию запускаем все тесты (unit + integration)
        cmd.append("tests/")
    
    # Добавляем флаг для цветного вывода (полезно в логах)
    cmd.append("--color=yes")
    
    # Устанавливаем переменную окружения для тестов
    env_vars = os.environ.copy()
    env_vars["TESTING_ENV"] = env
    
    logger.info(f"Запуск тестов: {' '.join(cmd)}, TESTING_ENV={env}")
    
    try:
        # Запускаем pytest с захватом вывода
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env_vars,
            cwd=os.getcwd(),
        )
        
        output = result.stdout
        error_output = result.stderr
        
        # Парсим результаты из вывода pytest
        test_result = _parse_pytest_output(output, error_output, result.returncode)
        
        logger.info(
            f"Тесты завершены: passed={test_result.passed}, "
            f"failed={test_result.failed}, skipped={test_result.skipped}, "
            f"errors={test_result.errors}"
        )
        
        # Сохраняем полный вывод в файл
        log_file_path = _save_test_log(output, error_output, test_type)
        
        return test_result, log_file_path
        
    except subprocess.TimeoutExpired as e:
        error_msg = f"Таймаут выполнения тестов ({timeout} сек)"
        logger.error(error_msg)
        
        # Создаем результат ошибки
        test_result = TestResult(
            passed=0,
            failed=0,
            skipped=0,
            errors=1,
            duration=timeout,
            output="",
            error_output=error_msg,
            success=False,
            timestamp=datetime.now().isoformat(),
        )
        
        # Сохраняем то, что успело выполниться
        partial_output = e.stdout.decode() if e.stdout else ""
        partial_error = e.stderr.decode() if e.stderr else ""
        log_file_path = _save_test_log(partial_output, partial_error, test_type)
        
        return test_result, log_file_path
        
    except Exception as e:
        error_msg = f"Ошибка запуска pytest: {e}"
        logger.error(error_msg, exc_info=True)
        
        test_result = TestResult(
            passed=0,
            failed=0,
            skipped=0,
            errors=1,
            duration=0.0,
            output="",
            error_output=error_msg,
            success=False,
            timestamp=datetime.now().isoformat(),
        )
        
        log_file_path = _save_test_log("", error_msg, test_type)
        
        return test_result, log_file_path


def _parse_pytest_output(
    stdout: str,
    stderr: str,
    returncode: int,
) -> TestResult:
    """
    Парсит вывод pytest и извлекает статистику.
    
    Пример строки с результатами:
    "5 passed, 2 failed, 3 skipped in 2.45s"
    или
    "10 passed in 1.23s"
    """
    # Поиск строки с результатами (обычно в конце вывода)
    summary_pattern = r"(\d+)\s+passed(?:,\s+(\d+)\s+failed)?(?:,\s+(\d+)\s+skipped)?(?:,\s+(\d+)\s+errors)?\s+in\s+([\d.]+)s"
    
    # Ищем в stdout
    match = re.search(summary_pattern, stdout)
    
    if not match:
        # Если не нашли в stdout, пробуем в stderr
        match = re.search(summary_pattern, stderr)
    
    if match:
        passed = int(match.group(1) or 0)
        failed = int(match.group(2) or 0)
        skipped = int(match.group(3) or 0)
        errors = int(match.group(4) or 0)
        duration = float(match.group(5) or 0.0)
    else:
        # Если не удалось распарсить, используем значения по умолчанию
        logger.warning("Не удалось распарсить результаты pytest")
        passed = 0
        failed = 1 if returncode != 0 else 0
        skipped = 0
        errors = 0
        duration = 0.0
    
    success = returncode == 0 and failed == 0 and errors == 0
    
    return TestResult(
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration=duration,
        output=stdout,
        error_output=stderr,
        success=success,
        timestamp=datetime.now().isoformat(),
    )


def _save_test_log(
    stdout: str,
    stderr: str,
    test_type: Optional[str],
) -> str:
    """
    Сохраняет вывод тестов во временный файл.
    
    Returns:
        Путь к созданному файлу
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_name = test_type or "all"
    
    # Создаем имя файла
    filename = f"test_results_{test_name}_{timestamp}.txt"
    
    # Используем системную временную директорию
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    
    # Формируем содержимое файла
    content = f"=== Test Results: {test_name.upper()} ===\n"
    content += f"Timestamp: {datetime.now().isoformat()}\n"
    content += f"Test Type: {test_type or 'all tests'}\n"
    content += "\n"
    
    if stdout:
        content += "=== STDOUT ===\n"
        content += stdout
        content += "\n\n"
    
    if stderr:
        content += "=== STDERR ===\n"
        content += stderr
        content += "\n\n"
    
    content += "=== END OF LOG ===\n"
    
    # Записываем в файл
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Логи сохранены: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Не удалось сохранить логи: {e}")
        return ""


def format_test_summary(result: TestResult) -> str:
    """
    Форматирует результаты тестов для отправки в Telegram.
    
    Returns:
        Markdown-форматированная строка с результатами
    """
    status_emoji = "✅" if result.success else "❌"
    status_text = "Успешно" if result.success else "Провалено"
    
    summary = f"{status_emoji} *Тесты: {status_text}*\n\n"
    summary += f"📊 *Статистика:*\n"
    summary += f"  ✅ Пройдено: {result.passed}\n"
    summary += f"  ❌ Провалено: {result.failed}\n"
    summary += f"  ⏭️ Пропущено: {result.skipped}\n"
    summary += f"  ⚠️ Ошибки: {result.errors}\n"
    summary += f"  ⏱️ Время: {result.duration:.2f}с\n"
    
    if result.failed > 0 or result.errors > 0:
        summary += f"\n⚠️ *Есть проблемы!*\n"
        summary += f"Проверьте логи для деталей.\n"
    
    summary += f"\n🕐 {result.timestamp}"
    
    return summary
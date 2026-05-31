## Why

Бот имеет критические функции, которые зависят от внешних API (Lobstr.io, GLM-5, Groq), работающие только на сервере Amvera. Отсутствие автоматизированных тестов увеличивает риск регрессий при изменениях и затрудняет отладку ошибок в production. Нужна система тестирования для проверки основных сценариев как локально (с моками), так и на сервере (с реальными API).

## What Changes

- Добавить pytest и необходимые зависимости (pytest-asyncio, pytest-mock)
- Создать структуру тестов: `tests/conftest.py`, `tests/unit/`, `tests/integration/`
- Добавить `ADMIN_IDS` в конфиг для управления тестовыми командами
- Создать модуль `services/test_runner.py` для запуска тестов на сервере
- Создать admin-обработчик `handlers/testing.py` с командой `/run_tests`
- Интегрировать testing router в bot.py
- Реализовать unit-тесты для моделей (Recipe, Group)
- Реализовать unit-тесты для сервисов (lobstr, parser, downloader)
- Реализовать интеграционные тесты для Lobstr API и полного pipeline
- Реализовать интеграционные тесты для транскрипции

## Capabilities

### New Capabilities
- `unit-testing`: Локальные unit-тесты с моками для проверки бизнес-логики без внешних зависимостей
- `integration-testing`: Серверные интеграционные тесты с реальными API для проверки end-to-end сценариев
- `test-orchestration`: Система запуска тестов через Telegram admin-команды и получения результатов

### Modified Capabilities
- `bot-configuration`: Добавление ADMIN_IDS для контроля над тестовыми командами

## Impact

- **config.py**: Добавить ADMIN_IDS и TESTING_ENV переменные окружения
- **requirements.txt**: Добавить pytest, pytest-asyncio, pytest-mock
- **bot.py**: Зарегистрировать testing router после существующих routers
- **tests/**: Новая директория с тестовой инфраструктурой
- **services/test_runner.py**: Новый модуль для запуска pytest
- **handlers/testing.py**: Новый admin-обработчик для команд управления тестами
- **CI/CD**: Возможность интеграции тестов в процессы деплоя (опционально)
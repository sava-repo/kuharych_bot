## Context

Бот развёрнут на Amvera и использует внешние API: Lobstr.io (парсинг Instagram), GLM-5 (LLM), Groq (транскрипция). Текущее состояние: нет автоматизированных тестов, все проверки выполняются вручную. Стейкхолдеры: разработчик (локально) и админ (на сервере). Ограничения: внешние API работают только с сервера, API-ключи в environment переменных.

## Goals / Non-Goals

**Goals:**
- Обеспечить локальное unit-тестирование без внешних зависимостей
- Обеспечить серверное интеграционное тестирование с реальными API
- Предоставить удобный интерфейс для запуска тестов через Telegram
- Минимизировать стоимость API-вызовов при тестировании

**Non-Goals:**
- Покрытие 100% кода тестами (только ключевые сценарии)
- Автоматизация CI/CD pipeline для тестов
- Создание mock серверов для внешних API
- Тестирование UI/UX бота

## Decisions

### Decision 1: Use pytest with pytest-asyncio and pytest-mock

**Rationale:**
- pytest — стандарт для Python тестирования с богатым экосистемой
- pytest-asyncio — необходим для тестирования async функций (aiogram, httpx)
- pytest-mock — удобный интерфейс для мокирования в pytest

**Alternatives considered:**
- unittest.mock без pytest-плагинов: более многословный синтаксис
- asynctest: устаревший проект, не поддерживает Python 3.11+

### Decision 2: Two-tier testing (unit + integration)

**Rationale:**
- Unit tests с моками позволяют быструю отладку локально
- Integration tests на сервере проверяют реальные API
- TESTING_ENV переменная позволяет отключать integration tests локально

**Alternatives considered:**
- Only unit tests: не найдёт проблемы с реальными API
- Only integration tests: не удобно для локальной разработки
- All tests always run:会增加成本 и время

### Decision 3: Subprocess for running pytest from bot

**Rationale:**
- Запуск pytest в subprocess не блокирует основной процесс бота
- Позволяет изолировать окружение тестов (TESTING_ENV=server)
- Упрощает capture stdout/stderr для отправки результатов

**Alternatives considered:**
- pytest embedded in bot process: блокирует бота, сложнее изоляция
- REST API endpoint: требует дополнительной инфраструктуры

### Decision 4: Admin command pattern (/run_tests)

**Rationale:**
- Естественный интерфейс для Telegram-бота
- ADMIN_IDS provides простой access control
- Аргументы позволяют фильтровать тесты по типу

**Alternatives considered:**
- Web UI: не соответствует Telegram-контексту
- Scheduled tests: не подходит для ad-hoc проверки

### Decision 5: Testing controls API call frequency

**Rationale:**
- Integration tests используют фиксированные тестовые данные
- Тесты проверяют success cases, не mass load
- pytest markers позволяют skip expensive tests при необходимости

**Alternatives considered:**
- Record/replay (VCR.py): не работает с динамическими данными (new Instagram URLs)
- Test accounts: сложность управления, API limits

## Risks / Trade-offs

**Risk: API costs for integration tests**
- **Mitigation:** Тесты используют минимальное количество вызовов, фиксированные тестовые данные, pytest markers для пропуска дорогих тестов

**Risk: Test execution blocks bot response**
- **Mitigation:** Subprocess execution с timeout (5 минут), acknowledgment message при старте, асинхронная отправка результатов

**Risk: Admin IDs in environment variables**
- **Mitigation:** Документация в .env.example, ограничение одним админом (252952086), recommendation использовать Amvera secret management

**Risk: Integration tests flakiness (network/API issues)**
- **Mitigation:** Retry logic в тестах, clear error messages, logs с timestamp, pytest markers для отдельных test suites

**Trade-off: Test coverage vs implementation time**
- Focus on critical paths (pipeline, Lobstr, models) over 100% coverage
- Unit tests first for quick feedback, integration tests for validation

**Trade-off: Local development convenience vs API realism**
- Mocks for fast local development, real API only on server
- TESTING_ENV variable allows switching between modes

## Migration Plan

1. **Setup phase (local):**
   - Добавить pytest зависимости в requirements.txt
   - Создать структуру tests/
   - Добавить ADMIN_IDS и TESTING_ENV в config.py
   - Написать unit-тесты, убедиться что проходят локально

2. **Implementation phase (local):**
   - Создать services/test_runner.py
   - Создать handlers/testing.py
   - Зарегистрировать testing router в bot.py
   - Тестировать admin-команды локально с моками

3. **Deployment phase (server):**
   - Деплой на Amvera
   - Добавить ADMIN_IDS=252952086 в environment variables
   - Запустить `/run_tests` через Telegram для проверки
   - Проверить что integration tests проходят

4. **Rollback strategy:**
   - Если `/run_tests` не работает: можно запускать pytest вручную через SSH на сервере
   - Если integration tests fail: можно откатить код, unit tests продолжают работать локально
   - Удалить testing router из bot.py для отключения функционала

## Open Questions

- **Q:** Нужно ли добавить телеметрию (логирование) запусков тестов?
  - **A:** Не в рамках этого change, можно добавить позже если потребуется
- **Q:** Как обрабатывать таймауты integration tests?
  - **A:** pytest timeout plugin, subprocess timeout в test_runner.py
- **Q:** Нужно ли хранить историю результатов тестов?
  - **A:** Не в рамках этого change, результаты отправляются только в Telegram
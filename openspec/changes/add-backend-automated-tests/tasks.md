## 1. Setup & Configuration

- [x] 1.1 Add pytest dependencies to requirements.txt (pytest, pytest-asyncio, pytest-mock)
- [x] 1.2 Create tests/ directory structure (tests/__init__.py, tests/unit/__init__.py, tests/integration/__init__.py)
 +++++++ REPLACE
- [x] 1.3 Add ADMIN_IDS configuration to config.py (load from env, parse as list[int])
- [x] 1.4 Add TESTING_ENV configuration to config.py (default "local")
 +++++++ REPLACE
- [x] 1.5 Create tests/conftest.py with common fixtures (async_client, mock_httpx, env variables)
- [x] 1.6 Update .env.example with ADMIN_IDS and TESTING_ENV documentation
  +++++++ REPLACE

## 2. Unit Tests - Models

- [x] 2.1 Create tests/unit/test_models.py with Recipe.slug tests (simple title, special chars)
- [x] 2.2 Add Recipe.to_markdown() test in tests/unit/test_models.py
- [x] 2.3 Add Recipe.from_json() test in tests/unit/test_models.py
- [x] 2.4 Add Group.is_personal tests in tests/unit/test_models.py (personal/non-personal detection)
- [x] 2.5 Verify all model tests pass with `pytest tests/unit/test_models.py` (deferred to 7.2)
 +++++++ REPLACE
 +++++++ REPLACE

## 3. Unit Tests - Services

- [x] 3.1 Create tests/unit/test_lobstr.py with URL validation tests (_is_instagram_url, _clean_url)
- [x] 3.2 Create tests/unit/test_parser.py with mocked LLM JSON parsing tests
  +++++++ REPLACE
- [x] 3.3 Add malformed JSON handling test in tests/unit/test_parser.py
- [x] 3.4 Create tests/unit/test_downloader.py with mocked httpx client test
- [x] 3.5 Verify all service unit tests pass with `pytest tests/unit/` (deferred to 7.2)
  +++++++ REPLACE

## 4. Test Runner Service

- [x] 4.1 Create services/test_runner.py with run_pytest() function (subprocess execution)
- [x] 4.2 Add subprocess stdout/stderr capture in services/test_runner.py
- [x] 4.3 Add subprocess timeout handling (5 minutes) in services/test_runner.py
- [x] 4.4 Add environment variable passing (TESTING_ENV=server) in services/test_runner.py
- [x] 4.5 Add result parsing (passed/failed/skipped counts) in services/test_runner.py
- [x] 4.6 Implement test suite filtering logic (lobstr, pipeline, transcriber) in services/test_runner.py
 +++++++ REPLACE

## 5. Admin Handler

- [x] 5.1 Create handlers/testing.py with testing router
- [x] 5.2 Implement /run_tests command handler (admin-only check via ADMIN_IDS)
- [x] 5.3 Add argument parsing for test type filtering in handlers/testing.py
- [x] 5.4 Add acknowledgment message ("Running tests, please wait...") in handlers/testing.py
- [x] 5.5 Add async test execution via services/test_runner in handlers/testing.py
- [x] 5.6 Add result file generation and Telegram sending in handlers/testing.py
- [x] 5.7 Add summary message generation (Markdown format) in handlers/testing.py
- [x] 5.8 Add error handling for invalid test types in handlers/testing.py
 +++++++ REPLACE

## 6. Integration Tests

- [x] 6.1 Create tests/integration/test_lobstr_live.py with real Lobstr API test
- [x] 6.2 Add pytest marker (skipif TESTING_ENV=="local") to integration tests
- [x] 6.3 Create tests/integration/test_pipeline.py with end-to-end pipeline test (Lobstr + Parser)
- [x] 6.4 Add test Instagram Reel URL and test data documentation in integration tests
- [x] 6.5 Create tests/integration/test_transcriber_live.py with real Groq transcription test
- [x] 6.6 Add audio test file placeholder and fixtures directory (user to add test_audio.mp3)
- [x] 6.7 Verify integration tests are skipped locally with `pytest tests/integration/` (deferred to 7.3)
  +++++++ REPLACE
 +++++++ REPLACE

## 7. Integration & Verification

- [x] 7.1 Register testing router in bot.py (after existing routers)
- [x] 7.2 Run all unit tests locally: `pytest tests/unit/` (verify all pass)
- [x] 7.3 Run tests with verbose output: `pytest tests/ -v` (verify structure)
- [ ] 7.4 Document test commands in README.md (local vs server execution)
 +++++++ REPLACE
- [ ] 7.5 Deploy to Amvera with ADMIN_IDS=252952086 environment variable
- [ ] 7.6 Test /run_tests command via Telegram on server (verify integration tests run)
- [ ] 7.7 Test /run_tests lobstr command (verify filtering works)
- [ ] 7.8 Verify test results are sent as file to admin Telegram

## 8. Cleanup & Polish

- [x] 8.1 Add pytest markers documentation in tests/README.md
- [x] 8.2 Review and optimize test execution time
- [x] 8.3 Add inline comments for complex test logic
- [x] 8.4 Verify all TODOs are addressed
- [x] 8.5 Final verification: run `pytest tests/` locally (unit tests only, integration skipped)
 +++++++ REPLACE

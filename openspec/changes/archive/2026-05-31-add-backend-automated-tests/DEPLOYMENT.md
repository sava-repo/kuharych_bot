# Deployment Guide for Backend Automated Tests

## Overview

This document describes the deployment and testing steps for the automated backend testing system.

## Current Status

✅ **Implementation Complete:** 47/50 tasks (94%)

**Completed:**
- All test infrastructure (pytest, fixtures, conftest)
- Unit tests for models and services
- Integration tests for Lobstr, Pipeline, Transcriber
- Test runner service (subprocess execution)
- Admin handler (`/run_tests` command)
- Documentation (README.md, .env.example)

**Remaining (Manual Steps):**
- [ ] Deploy to Amvera with ADMIN_IDS environment variable
- [ ] Test `/run_tests` command on server
- [ ] Verify integration tests run correctly
- [ ] Verify test results are sent as files

## Deployment Steps

### 1. Update Environment Variables on Amvera

Add these environment variables in Amvera:

```bash
# Required for testing
ADMIN_IDS=252952086
TESTING_ENV=server  # Enables integration tests

# Existing API keys (already set)
LOBSTR_API_KEY=your_lobstr_key
GROQ_API_KEY=your_groq_key
GLM_API_KEY=your_glm_key
```

### 2. Deploy to Amvera

Push changes and trigger deployment:

```bash
git add .
git commit -m "Add automated backend testing system"
git push origin main
```

Amvera will automatically deploy the updated code.

### 3. Verify Deployment

Check that the bot starts successfully:

```bash
# In Amvera logs, verify:
# - Bot starts without errors
# - All routers loaded (including testing router)
# - ADMIN_IDS loaded correctly
```

## Testing on Server

### Test 1: Unit Tests Only

```bash
# In Telegram (as admin):
/run_tests unit
```

**Expected:**
- Bot responds: "🧪 Запускаю unit, подождите..."
- After a few seconds: Summary with passed/failed counts
- Test log file sent as document
- All unit tests should pass

### Test 2: Integration Tests

```bash
# In Telegram (as admin):
/run_tests lobstr
```

**Expected:**
- Bot runs Lobstr API integration tests
- Tests call real Lobstr API
- Results sent with log file

```bash
/run_tests pipeline
```

**Expected:**
- Bot runs end-to-end pipeline tests
- Tests call Lobstr + Parser APIs
- Results sent with log file

```bash
/run_tests transcriber
```

**Expected:**
- Bot runs transcription tests (if test_audio.mp3 exists)
- Tests call Groq Whisper API
- Results sent with log file

### Test 3: All Tests

```bash
# In Telegram (as admin):
/run_tests
```

**Expected:**
- Runs all tests (unit + integration)
- Takes longer (up to 5 minutes)
- Comprehensive results sent

## Troubleshooting

### Issue: Tests skipped locally

**Symptom:** Integration tests show "SKIPPED" when running locally

**Solution:** This is expected behavior. Integration tests only run when `TESTING_ENV=server`.

### Issue: "You don't have permission" error

**Symptom:** Bot says "❌ У вас нет прав для запуска тестов"

**Solution:** Verify your Telegram ID is in `ADMIN_IDS` environment variable on Amvera.

### Issue: Tests timeout

**Symptom:** "❌ Таймаут выполнения тестов"

**Solution:** 
- Check Amvera logs for slow tests
- Increase timeout in `services/test_runner.py` if needed
- API calls may be slow (Groq, Lobstr)

### Issue: API key errors

**Symptom:** Tests fail with "API key not set" errors

**Solution:** Verify all API keys are set in Amvera environment variables:
- `LOBSTR_API_KEY`
- `GROQ_API_KEY`
- `GLM_API_KEY`

### Issue: Log file not sent

**Symptom:** Test results shown but no log file

**Solution:** 
- Check Amvera logs for file system errors
- Verify temp directory permissions
- Log files saved to system temp directory

## Test Coverage Summary

### Unit Tests (tests/unit/)

- **test_models.py**: Recipe.slug, Recipe.to_markdown(), Recipe.from_json(), Group.is_personal()
- **test_lobstr.py**: URL validation (_is_instagram_url, _clean_url)
- **test_parser.py**: LLM JSON parsing, malformed JSON handling
- **test_downloader.py**: HTTP client mocking

### Integration Tests (tests/integration/)

- **test_lobstr_live.py**: Real Lobstr API calls, URL validation, error handling
- **test_pipeline.py**: End-to-end recipe extraction (Lobstr + Parser)
- **test_transcriber_live.py**: Groq Whisper transcription, audio extraction

All integration tests are automatically skipped locally and only run when `TESTING_ENV=server`.

## Next Steps

1. **Deploy to Amvera** - Follow deployment steps above
2. **Run tests** - Use `/run_tests` commands to verify functionality
3. **Monitor results** - Check test results and logs for any issues
4. **Add test audio** - Optionally add `tests/fixtures/test_audio.mp3` for transcription tests
5. **Document findings** - Update documentation based on test results

## Contact

For questions or issues, check:
- README.md - User documentation
- tests/fixtures/README.md - Test data instructions
- Amvera logs - Runtime errors
- Telegram test results - Test execution details
## ADDED Requirements

### Requirement: Admin can run tests via Telegram command
The system SHALL provide `/run_tests` command accessible only to admins via ADMIN_IDS.

#### Scenario: Non-admin user tries to run tests
- **WHEN** user with ID not in ADMIN_IDS sends `/run_tests`
- **THEN** command is ignored
- **THEN** no response is sent

#### Scenario: Admin runs all integration tests
- **WHEN** admin sends `/run_tests`
- **THEN** pytest runs tests/integration/
- **THEN** results are sent as text file to admin
- **THEN** summary shows passed/failed/skipped counts

### Requirement: Test command supports filtering by test type
The system SHALL accept optional argument to run specific test suites.

#### Scenario: Admin runs only Lobstr tests
- **WHEN** admin sends `/run_tests lobstr`
- **THEN** pytest runs only Lobstr-related tests
- **THEN** other tests are skipped
- **THEN** results file shows only Lobstr test results

#### Scenario: Admin runs only pipeline tests
- **WHEN** admin sends `/run_tests pipeline`
- **THEN** pytest runs only pipeline integration tests
- **THEN** results show pipeline test results

#### Scenario: Admin runs only transcriber tests
- **WHEN** admin sends `/run_tests transcriber`
- **THEN** pytest runs only transcriber integration tests
- **THEN** results show transcriber test results

#### Scenario: Admin provides invalid test type
- **WHEN** admin sends `/run_tests invalid`
- **THEN** bot sends error message with valid options
- **THEN** no tests are executed

### Requirement: Test results include full logs
The system SHALL capture and send complete pytest output including tracebacks.

#### Scenario: Tests pass successfully
- **WHEN** all tests pass
- **THEN** summary message shows "All tests passed"
- **THEN** file contains full pytest output
- **THEN** file includes execution time per test

#### Scenario: Tests fail
- **WHEN** one or more tests fail
- **THEN** summary message shows failure count
- **THEN** file contains full pytest output with tracebacks
- **THEN** file includes error messages and stack traces

#### Scenario: Tests timeout
- **WHEN** test execution exceeds 5 minutes
- **THEN** pytest is terminated
- **THEN** error message sent to admin
- **THEN** partial results file is attached

### Requirement: Test runner handles subprocess execution
The system SHALL use subprocess to run pytest and capture stdout/stderr.

#### Scenario: Execute pytest command
- **WHEN** test runner is invoked
- **THEN** subprocess runs pytest with appropriate args
- **THEN** stdout and stderr are captured
- **THEN** return code is checked for success/failure

#### Scenario: Pass environment variables
- **WHEN** test runner is invoked
- **THEN** TESTING_ENV=server is passed to subprocess
- **THEN** API keys from environment are available to tests

### Requirement: Test runner generates readable report
The system SHALL format pytest output for readability in Telegram file.

#### Scenario: Generate summary
- **WHEN** pytest completes
- **THEN** summary includes total tests, passed, failed, skipped
- **THEN** summary includes total execution time
- **THEN** summary is formatted as Markdown

#### Scenario: Send results file
- **WHEN** pytest completes
- **THEN** full output is saved to temporary file
- **THEN** file is sent to admin via Telegram
- **THEN** temporary file is deleted after sending

### Requirement: Admin command responds with acknowledgment
The system SHALL acknowledge test start and send results when ready.

#### Scenario: Acknowledge test start
- **WHEN** admin sends `/run_tests`
- **THEN** bot sends message "Running tests, please wait..."
- **THEN** test execution begins

#### Scenario: Send results when complete
- **WHEN** test execution completes
- **THEN** bot sends file with results
- **THEN** bot sends summary message
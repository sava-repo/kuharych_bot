## ADDED Requirements

### Requirement: Integration tests run only on server
The system SHALL run integration tests with real API calls only when TESTING_ENV=server or explicitly requested.

#### Scenario: Skip integration tests locally
- **WHEN** TESTING_ENV=local (default)
- **THEN** tests in tests/integration/ are skipped
- **THEN** pytest shows "skipped" status for integration tests

#### Scenario: Run integration tests on server
- **WHEN** TESTING_ENV=server
- **THEN** tests in tests/integration/ execute
- **THEN** real API calls are made to Lobstr, GLM-5, Groq

### Requirement: Lobstr integration tests validate real API
The system SHALL test Lobstr.io API with real requests on server.

#### Scenario: Fetch Instagram reel caption
- **WHEN** valid Instagram Reel URL provided
- **THEN** Lobstr API returns caption text
- **THEN** caption is non-empty string
- **THEN** request completes within 60 seconds

#### Scenario: Handle invalid Instagram URL
- **WHEN** non-Instagram URL provided
- **THEN** Lobstr API returns error
- **THEN** appropriate exception is raised

### Requirement: Pipeline integration tests validate end-to-end flow
The system SHALL test complete recipe extraction pipeline on server.

#### Scenario: Extract recipe from Instagram Reel
- **WHEN** Instagram Reel URL is valid
- **THEN** Lobstr fetches caption
- **THEN** Caption is parsed by GLM-5
- **THEN** Recipe object is created with title, ingredients, steps
- **THEN** Recipe slug is generated
- **THEN** All steps complete without errors

#### Scenario: Handle video without recipe content
- **WHEN** Instagram Reel contains no recipe
- **THEN** Parser detects missing recipe structure
- **THEN** Appropriate error is returned

### Requirement: Transcriber integration tests validate real audio processing
The system SHALL test Groq transcription API with real audio files.

#### Scenario: Transcribe short audio clip
- **WHEN** valid audio file provided
- **THEN** Groq API returns transcription text
- **THEN** Transcription is in Russian language
- **THEN** Request completes within 30 seconds

#### Scenario: Handle unsupported audio format
- **WHEN** invalid audio file format provided
- **THEN** Transcriber raises appropriate exception
- **THEN** No API call is made

### Requirement: Integration tests use test data
The system SHALL provide test Instagram Reel URLs and audio files for integration testing.

#### Scenario: Use test Instagram Reel
- **WHEN** integration test runs
- **THEN** test uses known valid Instagram Reel URL
- **THEN** test data is documented in test comments

#### Scenario: Use test audio file
- **WHEN** transcription test runs
- **THEN** test uses provided sample audio file
- **THEN** audio file is included in repository
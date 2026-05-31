## ADDED Requirements

### Requirement: Unit tests use mocks for external dependencies
The system SHALL provide unit tests that mock all external API calls (Lobstr, GLM-5, Groq) to enable local testing without server dependencies.

#### Scenario: Run unit tests locally
- **WHEN** developer runs `pytest tests/unit/`
- **THEN** tests execute successfully without requiring API keys
- **THEN** all network calls are mocked using pytest-mock
- **THEN** tests cover models and services business logic

### Requirement: Recipe model tests validate slug generation
The system SHALL test Recipe.slug property generates URL-safe slugs from titles.

#### Scenario: Generate slug from simple title
- **WHEN** Recipe created with title "Мама мыла раму"
- **THEN** slug equals "mama-myla-ramu"

#### Scenario: Generate slug with special characters
- **WHEN** Recipe created with title "Паста Карбонара!!!"
- **THEN** slug equals "pasta-karbonara"

### Requirement: Recipe model tests validate serialization
The system SHALL test Recipe.to_markdown() and Recipe.from_json() methods.

#### Scenario: Serialize recipe to markdown
- **WHEN** Recipe has title, ingredients, steps
- **THEN** to_markdown() returns formatted markdown string

#### Scenario: Deserialize recipe from JSON
- **WHEN** JSON contains valid recipe data
- **THEN** from_json() returns Recipe object with correct fields

### Requirement: Group model tests validate personal group detection
The system SHALL test Group.is_personal property identifies personal groups.

#### Scenario: Detect personal group
- **WHEN** Group has group_id starting with "pers_"
- **THEN** is_personal returns True

#### Scenario: Detect non-personal group
- **WHEN** Group has group_id "group_123"
- **THEN** is_personal returns False

### Requirement: Lobstr service tests validate URL handling
The system SHALL test lobstr.py pure functions for URL validation and cleaning.

#### Scenario: Validate Instagram URL
- **WHEN** URL is "https://instagram.com/reel/ABC123"
- **THEN** _is_instagram_url returns True

#### Scenario: Validate non-Instagram URL
- **WHEN** URL is "https://youtube.com/watch?v=123"
- **THEN** _is_instagram_url returns False

#### Scenario: Clean URL with query parameters
- **WHEN** URL is "https://instagram.com/reel/ABC123?utm_source=test"
- **THEN** _clean_url returns "https://instagram.com/reel/ABC123"

### Requirement: Recipe parser tests validate JSON parsing
The system SHALL test recipe_parser.py with mocked LLM responses.

#### Scenario: Parse valid recipe JSON
- **WHEN** LLM returns valid recipe JSON with title, ingredients, steps
- **THEN** parser returns Recipe object with correct fields

#### Scenario: Handle malformed JSON
- **WHEN** LLM returns invalid JSON
- **THEN** parser raises appropriate exception

### Requirement: Downloader tests validate download logic
The system SHALL test downloader.py with mocked httpx client.

#### Scenario: Download Instagram video
- **WHEN** valid Instagram URL provided
- **THEN** downloader returns video bytes
- **THEN** httpx client called with correct headers
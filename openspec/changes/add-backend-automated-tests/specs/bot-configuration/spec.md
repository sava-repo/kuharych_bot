## ADDED Requirements

### Requirement: Configuration supports admin IDs
The system SHALL load ADMIN_IDS from environment variable for access control.

#### Scenario: Load admin IDs from environment
- **WHEN** ADMIN_IDS environment variable is set to "252952086"
- **THEN** config.ADMIN_IDS returns [252952086]
- **THEN** value is parsed as list of integers

#### Scenario: Handle multiple admin IDs
- **WHEN** ADMIN_IDS is set to "252952086,123456789"
- **THEN** config.ADMIN_IDS returns [252952086, 123456789]

#### Scenario: Default admin IDs empty
- **WHEN** ADMIN_IDS environment variable is not set
- **THEN** config.ADMIN_IDS returns empty list
- **THEN** admin functionality is disabled

### Requirement: Configuration supports testing environment
The system SHALL support TESTING_ENV variable to control test execution mode.

#### Scenario: Default to local testing
- **WHEN** TESTING_ENV environment variable is not set
- **THEN** config.TESTING_ENV returns "local"
- **THEN** integration tests are skipped by default

#### Scenario: Enable server testing
- **WHEN** TESTING_ENV is set to "server"
- **THEN** config.TESTING_ENV returns "server"
- **THEN** integration tests run with real API calls

### Requirement: Admin IDs are validated before use
The system SHALL validate user IDs against ADMIN_IDS before granting admin access.

#### Scenario: User is in admin list
- **WHEN** user_id is 252952086 and ADMIN_IDS is [252952086]
- **THEN** is_admin(user_id) returns True

#### Scenario: User is not in admin list
- **WHEN** user_id is 999999999 and ADMIN_IDS is [252952086]
- **THEN** is_admin(user_id) returns False

#### Scenario: Admin list is empty
- **WHEN** ADMIN_IDS is []
- **THEN** is_admin(any_user_id) returns False
- **THEN** no admin commands are available
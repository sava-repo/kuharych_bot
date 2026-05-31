## Context

Currently, the bot stores recipe references (slug, category) in the local SQLite database while the actual recipe files are stored in GitHub. When recipes are deleted directly from GitHub (not through the bot's "delete" button), the database still contains references to them. When the bot attempts to load recipe content via `gramax.get_recipe_content()`, GitHub returns a 404 error, which is currently raised as a generic `RuntimeError`. This exception is not caught in several handlers, resulting in stack traces being shown to users instead of friendly error messages.

The current implementation in `_try_get_random_recipe()` does catch 404 errors but automatically removes the recipe from the database, which could lead to data loss if GitHub is temporarily unavailable.

## Goals / Non-Goals

**Goals:**
- Gracefully handle 404 errors from GitHub API when recipes are not found
- Provide user-friendly error messages instead of stack traces
- Prevent automatic database cleanup to avoid data loss during temporary GitHub outages
- Allow users to continue using the bot when encountering deleted recipes (skip to next available recipe)

**Non-Goals:**
- Automatic cleanup of stale recipe records (to avoid data loss during temporary issues)
- Detection and removal of deleted recipes from all groups
- GitHub API retry logic (out of scope for this change)

## Decisions

### 1. Use specific exception class for 404 errors

**Decision:** Create a new `RecipeNotFoundError` exception class in `services/gramax.py` that inherits from `RuntimeError`.

**Rationale:**
- Allows handlers to distinguish between "recipe not found" (404) and other errors (network issues, permissions, etc.)
- Enables different handling strategies: skip vs retry vs show error message
- Maintains backward compatibility since it inherits from `RuntimeError`

**Alternatives considered:**
- Use HTTPException from httpx: Would require importing from another library and may not fit the current error handling pattern
- Use a custom error code in RuntimeError: Would require string parsing and is less type-safe

### 2. Skip deleted recipes instead of auto-removing

**Decision:** When a 404 error is encountered, skip the recipe and try the next available one instead of removing it from the database.

**Rationale:**
- Prevents data loss if GitHub is temporarily unavailable or returns false 404
- GitHub API typically returns 500/503 for temporary issues, but 404 might occur during CDN propagation delays
- Stale records don't prevent functionality - they're simply skipped during selection
- Can be cleaned up later via a manual process or background task

**Alternatives considered:**
- Remove stale records immediately: Risk of data loss during temporary outages
- Add retry logic: Adds complexity and doesn't solve the core issue (recipe truly deleted)

### 3. Create helper function for search operations

**Decision:** Implement `_try_get_recipe_from_slugs(slugs, category, group_id)` helper function in `handlers/menu.py` to centralize 404 handling for both search operations.

**Rationale:**
- Reduces code duplication between `handle_search_category()` and `handle_search_random()`
- Ensures consistent error handling across all recipe selection flows
- Easier to maintain and test

**Alternatives considered:**
- Duplicate logic in both handlers: Would lead to inconsistent behavior and maintenance burden
- Modify `_try_get_random_recipe()` to accept slugs list: Would change its semantics and make it harder to understand

### 4. Handle 404 in video processing by showing user-friendly message

**Decision:** In `_process_video()`, catch `RecipeNotFoundError` and show "⚠️ Recipe no longer available. Send link again to re-save" message.

**Rationale:**
- User already has the video link, so they can easily re-submit to re-save the recipe
- Clear communication that the specific recipe is gone
- Doesn't interrupt the overall flow

**Alternatives considered:**
- Automatically re-process the video: Could cause duplicate processing and user confusion
- Show generic error: Less helpful for user to understand what went wrong

## Risks / Trade-offs

**Risk:** Stale recipe records accumulate over time if recipes are frequently deleted from GitHub.

**Mitigation:** Implement a future cleanup mechanism (admin command or background task) that verifies recipe existence and removes truly deleted records.

**Risk:** Users might see "no recipes available" message even though database has stale records.

**Mitigation:** This is acceptable behavior - the bot shows what's actually available. Stale records don't confuse users as they're never shown.

**Trade-off:** Not auto-removing stale records means database may contain references to deleted recipes, but this is preferable to data loss during temporary outages.

## Migration Plan

**Deployment Steps:**
1. Add `RecipeNotFoundError` class to `services/gramax.py`
2. Update `gramax.get_recipe_content()` to raise `RecipeNotFoundError` for 404
3. Update all handlers to catch and handle `RecipeNotFoundError`
4. Update `_try_get_random_recipe()` to skip instead of remove
5. Deploy and monitor for any unhandled errors

**Rollback Strategy:**
- Revert to previous version that raises `RuntimeError` for 404
- Existing database records are unaffected by this change

**No database migration required** - this change only affects error handling logic.

## Open Questions

None - the design is straightforward and all key decisions have been made.
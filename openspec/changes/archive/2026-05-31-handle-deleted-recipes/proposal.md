## Why

When recipes are deleted directly from GitHub (not through the bot), the local database still contains references to them. When the bot tries to load the recipe content via GitHub API, it receives a 404 error, which causes an unhandled `RuntimeError` and shows a stack trace to the user instead of a friendly message. This degrades user experience and may cause confusion.

## What Changes

- Add a new `RecipeNotFoundError` exception class in `services/gramax.py` to specifically indicate when a recipe is not found (404)
- Update `gramax.get_recipe_content()` to raise `RecipeNotFoundError` instead of generic `RuntimeError` for 404 responses
- Modify `_try_get_random_recipe()` in `handlers/menu.py` to skip deleted recipes instead of automatically removing them from the database
- Create a helper function `_try_get_recipe_from_slugs()` for search operations that gracefully handles 404 errors by skipping affected recipes
- Update `_process_video()` in `handlers/link.py` to catch `RecipeNotFoundError` and provide a user-friendly error message
- Update `handle_move()` in `handlers/buttons.py` to handle `RecipeNotFoundError` gracefully

## Capabilities

### New Capabilities

- (none - this is error handling improvement, not a new capability)

### Modified Capabilities

- (none - no spec-level behavior changes; only improved error handling for existing flows)

## Impact

- **services/gramax.py**: Add `RecipeNotFoundError` exception class and modify `get_recipe_content()` to use it
- **handlers/menu.py**: Update `_try_get_random_recipe()`, add new `_try_get_recipe_from_slugs()` helper, modify `handle_search_category()` and `handle_search_random()`
- **handlers/link.py**: Update `_process_video()` to catch and handle `RecipeNotFoundError`
- **handlers/buttons.py**: Update `handle_move()` to handle `RecipeNotFoundError`
- **User Experience**: Users will see friendly error messages instead of stack traces when encountering deleted recipes
- **Data Integrity**: No automatic cleanup of stale records to avoid data loss during temporary GitHub outages
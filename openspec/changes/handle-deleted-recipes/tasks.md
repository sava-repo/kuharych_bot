  ## 1. Add RecipeNotFoundError exception

  - [x] 1.1 Add `RecipeNotFoundError` class to `services/gramax.py` that inherits from `RuntimeError`
  - [x] 1.2 Update `gramax.get_recipe_content()` to raise `RecipeNotFoundError` instead of `RuntimeError` when status_code is 404
  - [x] 1.3 Ensure all other errors still raise `RuntimeError` (500, 503, network issues, etc.)

  ## 2. Update handlers/menu.py

  - [x] 2.1 Modify `_try_get_random_recipe()` to catch `RecipeNotFoundError` and `continue` instead of calling `gm.remove_recipe_from_group()`
  - [x] 2.2 Create helper function `_try_get_recipe_from_slugs(slugs: list[str], category: str, group_id: str) -> tuple[str, str] | None` that:
  - Shuffles the slugs list
  - Iterates through slugs, calling `gramax.get_recipe_content()`
  - Catches `RecipeNotFoundError` and continues to next slug
  - Returns `(slug, content)` on success or `None` if all fail
  - [x] 2.3 Update `handle_search_category()` to use `_try_get_recipe_from_slugs()` instead of directly calling `gramax.get_recipe_content()`
  - [x] 2.4 Update `handle_search_random()` to use `_try_get_recipe_from_slugs()` instead of directly calling `gramax.get_recipe_content()`

  ## 3. Update handlers/link.py

  - [x] 3.1 Add import for `RecipeNotFoundError` from `services.gramax` (not needed - already imported via `gramax` module)
  - [x] 3.2 In `_process_video()`, wrap the existing recipe content loading logic (lines 191 and 197) in try/except block
  - [x] 3.3 Catch `RecipeNotFoundError` in the try/except block and return with user-friendly error message "⚠️ Рецепт по этой ссылке больше не доступен. Отправьте ссылку заново для повторного сохранения"

## 4. Update handlers/buttons.py

- [x] 4.1 Add import for `RecipeNotFoundError` from `services.gramax` (not needed - already imported via `gramax` module)
- [x] 4.2 In `handle_move()`, wrap the `gramax.get_recipe_content()` call (line 267) in try/except block
- [x] 4.3 Catch `RecipeNotFoundError` and display user-friendly message "⚠️ Рецепт не найден. Возможно, он был удалён."

## 5. Testing

- [ ] 5.1 Test that deleted recipes in random selection are skipped without errors
- [ ] 5.2 Test that deleted recipes in search results are skipped without errors
- [ ] 5.3 Test that video processing with a deleted existing recipe shows user-friendly error
- [ ] 5.4 Test that moving a deleted recipe shows user-friendly error
- [ ] 5.5 Verify that stale records remain in database after encountering 404 errors
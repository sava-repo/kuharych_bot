"""Разовая утилита: проверка синтаксиса всех файлов проекта"""
import py_compile
import sys

files = [
    "exceptions.py",
    "constants.py",
    "config.py",
    "models/recipe.py",
    "models/group.py",
    "models/__init__.py",
    "handlers/keyboards.py",
    "handlers/link.py",
    "handlers/buttons.py",
    "handlers/menu.py",
    "handlers/groups.py",
    "services/__init__.py",
    "services/database.py",
    "services/group_manager.py",
    "services/recipe_parser.py",
    "services/recipe_pipeline.py",
    "services/gramax.py",
    "services/hiker.py",
    "services/transcriber.py",
    "services/cache.py",
    "services/rotation.py",
    "bot.py",
]

ok = 0
failed = 0
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"  OK  {f}")
        ok += 1
    except py_compile.PyCompileError as e:
        print(f" FAIL  {f}: {e}")
        failed += 1

print(f"\n{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
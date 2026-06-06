"""Морфологическая нормализация русского текста через pymorphy2.

Используется для поиска рецептов по ингредиентам без учёта падежей,
чисел и прочих форм слов. Лемматизация применяется и к индексу ингредиентов
при сохранении рецепта, и к запросу пользователя при поиске.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

try:
    # pymorphy3 — современный форк для Python 3.11+
    import pymorphy3 as pymorphy
except ImportError:  # pragma: no cover - fallback для старых окружений
    import pymorphy2 as pymorphy  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# Токенизация: буквы (включая кириллицу) и цифры, минимум 1 символ.
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)

# Часть речи, которые мы исключаем из набора лемм:
# предлоги, союзы, частицы, междометия, местоимения.
_STOP_POS = {"PREP", "CONJ", "PRCL", "INTJ", "NPRO"}

# Singleton MorphAnalyzer (тяжёлый при инициализации).
_morph: "pymorphy.MorphAnalyzer | None" = None


def _get_morph() -> "pymorphy.MorphAnalyzer":
    """Возвращает singleton MorphAnalyzer (lazy init)."""
    global _morph
    if _morph is None:
        logger.debug("Initializing pymorphy MorphAnalyzer")
        _morph = pymorphy.MorphAnalyzer()
    return _morph


@lru_cache(maxsize=4096)
def _normalize_token(token: str) -> tuple[str, bool]:
    """Возвращает (lemma, is_content_word) для одного токена.

    is_content_word=False для цифр и стоп-слов (предлоги, союзы и т.п.).
    Кэшируется, т.к. типовые слова («яйцо», «молоко») повторяются.
    """
    if token.isdigit():
        return "", False

    morph = _get_morph()
    parsed = morph.parse(token)
    if not parsed:
        return token.lower(), True

    parse = parsed[0]
    if parse.tag.POS in _STOP_POS:
        return "", False

    lemma = parse.normal_form or token.lower()
    return lemma, True


def normalize_word(word: str) -> str:
    """Возвращает нормальную форму однословного запроса.

    Для цифр и стоп-слов возвращает пустую строку.

    >>> normalize_word("яйца")
    'яйцо'
    >>> normalize_word("индейка")
    'индейка'
    >>> normalize_word("10")
    ''
    """
    if not word:
        return ""
    token = word.strip()
    if not token:
        return ""
    # Если ввели фразу — берём первое значимое слово
    tokens = _TOKEN_RE.findall(token)
    for tok in tokens:
        lemma, is_content = _normalize_token(tok)
        if is_content and lemma:
            return lemma
    return ""


def lemmatize_text(text: str) -> list[str]:
    """Токенизация + лемматизация строки; возвращает уникальные леммы по порядку.

    Цифры и стоп-лова (предлоги, союзы, местоимения) исключаются.

    >>> lemmatize_text("10 яиц")
    ['яйцо']
    >>> lemmatize_text("филе индейки")
    ['филе', 'индейка']
    >>> lemmatize_text("куриная грудка")
    ['куриный', 'грудка']
    >>> lemmatize_text("")
    []
    """
    if not text:
        return []

    tokens = _TOKEN_RE.findall(text)
    seen: set[str] = set()
    lemmas: list[str] = []

    for token in tokens:
        lemma, is_content = _normalize_token(token)
        if not is_content or not lemma:
            continue
        if lemma in seen:
            continue
        seen.add(lemma)
        lemmas.append(lemma)

    return lemmas
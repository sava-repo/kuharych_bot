"""Unit-тесты для services/lemmatizer.py."""

from services.lemmatizer import lemmatize_text, normalize_word


class TestNormalizeWord:
    def test_яйца_rightarrow_яйцо(self):
        assert normalize_word("яйца") == "яйцо"

    def test_индейка_само_себе(self):
        assert normalize_word("индейка") == "индейка"

    def test_индейку_родительный(self):
        assert normalize_word("индейку") == "индейка"

    def test_молока_rightarrow_молоко(self):
        assert normalize_word("молока") == "молоко"

    def test_digit_returns_empty(self):
        assert normalize_word("10") == ""

    def test_empty_returns_empty(self):
        assert normalize_word("") == ""

    def test_whitespace_returns_empty(self):
        assert normalize_word("   ") == ""

    def test_phrase_takes_first_content_word(self):
        # «куриная грудка» → первая знаменательная лемма «куриный»
        assert normalize_word("куриная грудка") == "куриный"

    def test_only_stopwords_returns_empty(self):
        # «и» — союз, должен вернуть пустую строку
        assert normalize_word("и") == ""


class TestLemmatizeText:
    def test_empty(self):
        assert lemmatize_text("") == []

    def test_only_digits_filtered(self):
        assert lemmatize_text("10") == []
        assert lemmatize_text("300") == []

    def test_10_яиц(self):
        result = lemmatize_text("10 яиц")
        assert "яйцо" in result
        assert "10" not in result

    def test_филе_индейки(self):
        result = lemmatize_text("филе индейки")
        assert "филе" in result
        assert "индейка" in result

    def test_куриная_грудка(self):
        result = lemmatize_text("куриная грудка")
        assert "куриный" in result
        assert "грудка" in result

    def test_deduplication_preserves_order(self):
        # «яйцо яйца» → обе леммы «яйцо», должна остаться одна
        result = lemmatize_text("яйцо яйца")
        assert result == ["яйцо"]

    def test_stops_filterered(self):
        # «молоко с солью» — «с» это предлог, останутся «молоко» и «соль»
        result = lemmatize_text("молоко с солью")
        assert "молоко" in result
        assert "соль" in result
        # предлог «с» не должен появиться как лемма
        assert all(len(lemma) > 1 for lemma in result)
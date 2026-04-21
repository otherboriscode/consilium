from consilium.tokens import count_tokens


def test_count_tokens_english():
    assert count_tokens("Hello, world!") > 0


def test_count_tokens_cyrillic():
    assert count_tokens("Привет мир") > 0


def test_count_tokens_empty_string_returns_zero():
    assert count_tokens("") == 0

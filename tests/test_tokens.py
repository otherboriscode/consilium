from consilium.tokens import count_tokens


def test_count_tokens_openai_like():
    # tiktoken cl100k_base for GPT/OpenRouter non-anthropic
    assert count_tokens("Hello, world!", model="gpt-4o") > 0


def test_count_tokens_anthropic():
    # Uses anthropic client's token counter
    tokens = count_tokens("Привет мир", model="claude-opus-4-7")
    assert tokens > 0


def test_count_tokens_fallback():
    # Unknown model → cl100k_base fallback
    assert count_tokens("test", model="some-unknown-model") > 0

from consilium_server.bot.handlers.run_debate import _extract_tldr


def test_extract_tldr_between_h1_headers():
    md = (
        "---\nfrontmatter\n---\n\n"
        "# Тема\n\nsome topic\n\n"
        "# Раунд 0\n\narchitect text\n\n"
        "# Синтез\n\n"
        "# TL;DR\n\n"
        "Это краткое резюме\n\n"
        "# Точки консенсуса\n"
        "- foo\n"
    )
    tldr = _extract_tldr(md)
    assert "Это краткое резюме" in tldr
    assert "Точки консенсуса" not in tldr
    assert "architect text" not in tldr


def test_extract_tldr_missing_returns_empty():
    assert _extract_tldr("no header here") == ""


def test_extract_tldr_handles_h2_header_style():
    md = "## TL;DR\n\nShort summary\n\n## Next\n"
    assert "Short summary" in _extract_tldr(md)


def test_extract_tldr_truncates_very_long_text():
    body = "x" * 3000
    md = f"# TL;DR\n{body}\n"
    assert len(_extract_tldr(md)) <= 2000

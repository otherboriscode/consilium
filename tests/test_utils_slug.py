from consilium.utils.slug import slugify


def test_slug_latin():
    assert slugify("Hello World") == "hello-world"


def test_slug_cyrillic_preserved():
    assert slugify("Концепция продукта") == "концепция-продукта"


def test_slug_mixed_latin_cyrillic():
    assert slugify("Tanaa Артасава Tropical") == "tanaa-артасава-tropical"


def test_slug_truncates_at_max_length():
    assert len(slugify("x" * 100, max_length=60)) == 60


def test_slug_collapses_separators():
    assert slugify("a---b  c") == "a-b-c"


def test_slug_empty_fallback():
    assert slugify("") == "debate"
    assert slugify("   ") == "debate"
    assert slugify("!!!") == "debate"


def test_slug_preserves_yo():
    assert slugify("Ёлка зелёная") == "ёлка-зелёная"

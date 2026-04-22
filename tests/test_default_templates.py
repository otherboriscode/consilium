import pytest

from consilium.templates import list_templates, load_template


@pytest.mark.parametrize(
    "name",
    [
        "product_concept",
        "positioning",
        "pricing_strategy",
        "unit_economics",
        "brand_check",
        "quick_check",
        "book_chapter_review",
    ],
)
def test_default_template_loads_and_builds_config(name):
    t = load_template(name)
    cfg = t.build_config(topic="test topic")
    assert len(cfg.participants) >= 3
    assert cfg.judge.model
    for p in cfg.participants:
        assert "ФОРМАТ ОТВЕТА" in p.system_prompt, (
            f"{name}.{p.role} missing format rules"
        )


def test_list_templates_includes_all_seven():
    names = list_templates()
    for expected in (
        "product_concept",
        "positioning",
        "pricing_strategy",
        "unit_economics",
        "brand_check",
        "quick_check",
        "book_chapter_review",
    ):
        assert expected in names


def test_unit_economics_uses_deep_mode_for_reasoners():
    t = load_template("unit_economics")
    cfg = t.build_config(topic="t")
    by_role = {p.role: p for p in cfg.participants}
    # Glubokij razbor — engineer and analyst both use extended thinking.
    assert by_role["engineer"].deep is True
    assert by_role["analyst"].deep is True


def test_quick_check_is_one_round_with_three_participants():
    t = load_template("quick_check")
    cfg = t.build_config(topic="t")
    assert cfg.rounds == 1
    assert len(cfg.participants) == 3

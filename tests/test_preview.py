from consilium.default_council import build_default_council
from consilium.preview import PreviewInfo, build_preview


def test_preview_shows_all_participants_with_modes():
    config = build_default_council(topic="Test topic")
    preview = build_preview(config)
    for p in config.participants:
        assert p.role in preview.text
    assert "Fast" in preview.text or "Deep" in preview.text


def test_preview_shows_cost_and_duration():
    config = build_default_council(topic="Test topic")
    preview = build_preview(config)
    assert "$" in preview.text
    assert "мин" in preview.text.lower() or "min" in preview.text.lower()
    assert preview.estimated_cost_usd > 0
    assert preview.estimated_duration_seconds > 0


def test_preview_shows_fit_when_context_provided():
    config = build_default_council(topic="T")
    # moderate-sized context — everyone should fit "full"
    preview = build_preview(config, context_block="x " * 5_000)
    assert "fit:" in preview.text.lower() or "fit" in preview.text.lower()
    assert "full" in preview.text.lower()


def test_preview_info_is_dataclass():
    config = build_default_council(topic="t")
    preview = build_preview(config)
    assert isinstance(preview, PreviewInfo)
    assert isinstance(preview.text, str)


def test_preview_topic_is_truncated_if_long():
    long_topic = "x" * 200
    config = build_default_council(topic=long_topic)
    preview = build_preview(config)
    # Only first ~80 chars appear; full topic is NOT in preview.
    assert long_topic not in preview.text
    assert "..." in preview.text

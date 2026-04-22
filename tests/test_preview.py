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


def test_preview_excluded_participant_has_zero_cost_line():
    """Stubbing compute_fit to return 'exclude' for a role should show
    EXCLUDED and contribute $0.00 to that line."""
    from consilium.context.fit import FitDecision
    import consilium.preview as pv

    cfg = build_default_council(topic="t")
    orig = pv.compute_fit

    def _stub(*, participant, **kwargs):
        if participant.role == "engineer":
            return FitDecision(kind="exclude", reason="stub")
        return orig(participant=participant, **kwargs)

    pv.compute_fit = _stub  # type: ignore[assignment]
    try:
        preview = build_preview(cfg, context_block="x " * 10_000)
    finally:
        pv.compute_fit = orig  # type: ignore[assignment]

    # The `engineer` row must show EXCLUDED with $0.00
    engineer_line = next(line for line in preview.text.splitlines() if "engineer" in line)
    assert "EXCLUDED" in engineer_line
    assert "~$0.00" in engineer_line


def test_preview_shows_summary_bucket_when_participants_need_compression():
    """When a participant lands in fit=summary, a 📦 line appears with
    Haiku compression cost and the number of unique target buckets."""
    from consilium.context.fit import FitDecision
    import consilium.preview as pv

    cfg = build_default_council(topic="t")
    orig = pv.compute_fit

    def _stub(*, participant, **kwargs):
        # Force everyone into the same 30K summary bucket.
        return FitDecision(kind="summary", summary_target_tokens=30_000)

    pv.compute_fit = _stub  # type: ignore[assignment]
    try:
        preview = build_preview(cfg, context_block="x " * 50_000)
    finally:
        pv.compute_fit = orig  # type: ignore[assignment]

    assert "Сжатие контекста" in preview.text
    assert "× 1 бакет" in preview.text


def test_preview_deduplicates_summary_targets():
    """Two different targets → two Haiku calls; display '× 2 бакета'."""
    from consilium.context.fit import FitDecision
    import consilium.preview as pv

    cfg = build_default_council(topic="t")
    orig = pv.compute_fit
    roles_sorted = [p.role for p in cfg.participants]

    def _stub(*, participant, **kwargs):
        # First half → 20K bucket, second half → 40K bucket.
        idx = roles_sorted.index(participant.role)
        target = 20_000 if idx < len(roles_sorted) // 2 else 40_000
        return FitDecision(kind="summary", summary_target_tokens=target)

    pv.compute_fit = _stub  # type: ignore[assignment]
    try:
        preview = build_preview(cfg, context_block="x " * 50_000)
    finally:
        pv.compute_fit = orig  # type: ignore[assignment]

    assert "× 2 бакета" in preview.text


def test_preview_without_context_has_no_summary_line():
    cfg = build_default_council(topic="t")
    preview = build_preview(cfg)
    assert "Сжатие контекста" not in preview.text
    assert "EXCLUDED" not in preview.text

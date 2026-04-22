from consilium.default_council import build_default_council
from consilium.models import JobConfig


def test_default_council_has_five_participants_and_judge():
    cfg = build_default_council(topic="Some topic")
    assert isinstance(cfg, JobConfig)
    assert len(cfg.participants) == 5
    assert {p.role for p in cfg.participants} == {
        "architect",
        "marketer",
        "analyst",
        "engineer",
        "devil_advocate",
    }
    assert cfg.judge.model.startswith("claude-haiku")


def test_default_council_models_match_design():
    cfg = build_default_council(topic="t")
    by_role = {p.role: p for p in cfg.participants}
    assert by_role["architect"].model == "claude-opus-4-7"
    assert by_role["marketer"].model == "openai/gpt-5"
    assert by_role["analyst"].model == "google/gemini-2.5-pro"
    assert by_role["engineer"].model == "deepseek/deepseek-r1"
    assert by_role["devil_advocate"].model == "x-ai/grok-4"


def test_default_council_all_system_prompts_in_russian():
    cfg = build_default_council(topic="t")
    for p in cfg.participants:
        assert any("а" <= ch.lower() <= "я" for ch in p.system_prompt)
    assert any("а" <= ch.lower() <= "я" for ch in cfg.judge.system_prompt)


def test_default_council_reasoning_models_have_adequate_max_tokens():
    """Reasoning models (gpt-5, gemini-2.5-pro, deepseek-r1, grok-4) burn hidden
    tokens on thinking before emitting visible output. The default 1200 is not
    enough — marketer (gpt-5) came back empty and analyst (gemini-2.5-pro) got
    truncated mid-sentence in the first real-world debate (2026-04-21).
    """
    cfg = build_default_council(topic="t")
    by_role = {p.role: p for p in cfg.participants}
    # Heavy-reasoning models (gpt-5, gemini-2.5-pro, grok-4) need ≥6000.
    assert by_role["marketer"].max_tokens >= 6000
    assert by_role["analyst"].max_tokens >= 6000
    assert by_role["devil_advocate"].max_tokens >= 6000
    # Moderate reasoning (Opus non-deep, deepseek-r1) — 3500.
    assert by_role["architect"].max_tokens >= 3500
    assert by_role["engineer"].max_tokens >= 3500


def test_default_council_prompts_forbid_h1():
    cfg = build_default_council(topic="t")
    for p in cfg.participants:
        assert "не используй заголовки первого уровня" in p.system_prompt.lower() or \
               "не используй заголовки" in p.system_prompt.lower()


def test_default_council_devil_advocate_prompt_mentions_breaking_consensus():
    cfg = build_default_council(topic="t")
    devil = next(p for p in cfg.participants if p.role == "devil_advocate")
    assert "ломать консенсус" in devil.system_prompt.lower()
    assert "новые слабости конкретно в позициях других" in devil.system_prompt.lower()


def test_default_council_judge_prompt_caps_top_score():
    cfg = build_default_council(topic="t")
    assert "максимум один участник" in cfg.judge.system_prompt.lower()

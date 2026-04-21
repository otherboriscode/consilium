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

from pathlib import Path

import pytest

from consilium.models import JobConfig
from consilium.templates import Template, TemplateError, list_templates, load_template

FIXTURES = Path(__file__).parent / "fixtures" / "templates"


_MIN_YAML = """
name: foo
title: Test
description: Test template
participants:
  - model: claude-opus-4-7
    role: alpha
    system_prompt: "Role A."
  - model: openai/gpt-5
    role: beta
    system_prompt: "Role B."
judge:
  model: claude-haiku-4-5
  system_prompt: "Judge."
rounds: 2
"""


def test_load_minimal_template():
    t = load_template("minimal", search_dirs=[FIXTURES])
    assert isinstance(t, Template)
    assert t.name == "minimal"
    assert len(t.participants) == 2
    assert t.judge.model


def test_template_builds_job_config():
    t = load_template("minimal", search_dirs=[FIXTURES])
    config = t.build_config(topic="test topic")
    assert isinstance(config, JobConfig)
    assert config.topic == "test topic"
    assert config.template_name == "minimal"


def test_template_version_is_content_hash():
    t = load_template("minimal", search_dirs=[FIXTURES])
    assert len(t.version) >= 8
    t2 = load_template("minimal", search_dirs=[FIXTURES])
    assert t.version == t2.version


def test_load_unknown_template_raises():
    with pytest.raises(TemplateError, match="not found"):
        load_template("does_not_exist", search_dirs=[FIXTURES])


def test_load_invalid_template_raises():
    with pytest.raises(TemplateError):
        load_template("invalid_no_judge", search_dirs=[FIXTURES])


def test_list_templates_returns_sorted_names():
    names = list_templates(search_dirs=[FIXTURES])
    assert "minimal" in names
    assert names == sorted(names)


def test_custom_dir_overrides_default(tmp_path):
    default = tmp_path / "default"
    default.mkdir()
    (default / "foo.yaml").write_text(_MIN_YAML.replace("Role A", "DEFAULT"))

    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "foo.yaml").write_text(_MIN_YAML.replace("Role A", "CUSTOM"))

    t = load_template("foo", search_dirs=[custom, default])
    assert "CUSTOM" in t.participants[0].system_prompt


def test_content_hash_stable_across_eol_styles():
    from consilium.templates import _content_hash
    assert _content_hash("name: foo\nvalue: 1\n") == _content_hash(
        "name: foo\r\nvalue: 1\r\n"
    )
    assert _content_hash("a\nb\n") == _content_hash("a\rb\r")


def test_content_hash_stable_across_trailing_whitespace():
    from consilium.templates import _content_hash
    a = _content_hash("name: foo\nvalue: 1")
    b = _content_hash("name: foo\nvalue: 1\n")
    c = _content_hash("name: foo\nvalue: 1\n\n\n")
    d = _content_hash("name: foo\nvalue: 1   \n\n")
    assert a == b == c == d


def test_content_hash_different_for_semantic_change():
    from consilium.templates import _content_hash
    assert _content_hash("name: foo\nvalue: 1\n") != _content_hash(
        "name: foo\nvalue: 2\n"
    )

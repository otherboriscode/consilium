"""Tests for `consilium_client.config.load_config`."""
from __future__ import annotations

import pytest

from consilium_client.config import load_config


def test_env_overrides_file(tmp_path, monkeypatch):
    cfg = tmp_path / "client.yaml"
    cfg.write_text("api_base: http://file.example\ntoken: from-file\n")
    monkeypatch.setenv("CONSILIUM_API_BASE", "http://env.example")
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "from-env")
    result = load_config(path=cfg)
    assert result.api_base == "http://env.example"
    assert result.token == "from-env"


def test_file_used_when_env_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("CONSILIUM_API_BASE", raising=False)
    monkeypatch.delenv("CONSILIUM_API_TOKEN", raising=False)
    cfg = tmp_path / "client.yaml"
    cfg.write_text("api_base: http://only-file.example\ntoken: file-only\n")
    result = load_config(path=cfg)
    assert result.api_base == "http://only-file.example"
    assert result.token == "file-only"


def test_missing_both_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("CONSILIUM_API_BASE", raising=False)
    monkeypatch.delenv("CONSILIUM_API_TOKEN", raising=False)
    cfg = tmp_path / "nonexistent.yaml"
    with pytest.raises(ValueError, match="Client config incomplete"):
        load_config(path=cfg)


def test_partial_env_combines_with_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "env-token")
    monkeypatch.delenv("CONSILIUM_API_BASE", raising=False)
    cfg = tmp_path / "client.yaml"
    cfg.write_text("api_base: http://from-file.example\n")
    result = load_config(path=cfg)
    assert result.api_base == "http://from-file.example"
    assert result.token == "env-token"


def test_timeout_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_BASE", "http://x")
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "t")
    monkeypatch.setenv("CONSILIUM_API_TIMEOUT", "60")
    result = load_config(path=tmp_path / "none.yaml")
    assert result.timeout_seconds == 60.0

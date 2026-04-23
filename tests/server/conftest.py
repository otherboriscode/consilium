"""
Shared fixtures for server tests: authed TestClient, isolated archive dir,
fresh singletons, and a fake ProviderRegistry so POST /jobs doesn't touch
real LLMs in unit tests.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from consilium.providers.base import BaseProvider, CallResult, CallUsage, Message
from consilium_server.api import state as state_module
from consilium_server.api.main import app


@pytest.fixture(autouse=True)
def reset_server_state(monkeypatch):
    """Each test starts with a clean singleton + tight concurrency bounds."""
    state_module._state = None
    # Default test-friendly state: no rate-limit, 3 concurrent.
    state_module.reset_state_for_tests(max_concurrent=3, min_seconds_between=0)
    yield
    state_module._state = None


@pytest.fixture
def authed_env(tmp_path, monkeypatch):
    """Fully-configured test environment: auth token + isolated data dir +
    fake API keys (never used because providers are mocked below)."""
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "test-token-xyz")
    monkeypatch.setenv("CONSILIUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-anthropic")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-openrouter")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-fake")
    return tmp_path


@pytest.fixture
def authed_headers(authed_env):
    return {"Authorization": "Bearer test-token-xyz"}


@pytest.fixture
def api_client(authed_env):
    return TestClient(app)


class _FakeProvider(BaseProvider):
    """Returns a canned CallResult immediately — no network, tiny cost."""

    name = "fake"

    def __init__(self, text: str = "ok") -> None:
        self._text = text

    async def call(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        deep: bool = False,
        cache_last_system_block: bool = True,
        timeout_seconds: float = 300.0,
    ) -> CallResult:
        return CallResult(
            text=self._text,
            usage=CallUsage(input_tokens=50, output_tokens=20),
            model=model,
            finish_reason="stop",
            duration_seconds=0.01,
        )


class _FakeRegistry:
    """get_provider returns a provider that responds with sensible defaults.
    Judge gets the sample judge markdown so the parser produces scores."""

    def __init__(self) -> None:
        from pathlib import Path

        fixture_path = (
            Path(__file__).parent.parent
            / "fixtures"
            / "judge_output_sample.md"
        )
        self._judge_text = fixture_path.read_text(encoding="utf-8")

    def get_provider(self, model: str) -> BaseProvider:
        if model.startswith("claude-haiku"):
            return _FakeProvider(text=self._judge_text)
        return _FakeProvider(text="stubbed participant reply")


@pytest.fixture
def mock_registry(monkeypatch):
    """Monkeypatch the API-layer registry builder so submissions never touch
    real providers. Returns the singleton so tests can inspect it if they want."""
    fake = _FakeRegistry()

    def _build():
        return fake

    monkeypatch.setattr(
        "consilium_server.api.routes.jobs._build_registry", _build
    )
    return fake

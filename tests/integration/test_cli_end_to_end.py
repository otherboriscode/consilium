"""
CLI ↔ API integration: subprocess `consilium ...` against an in-process
TestClient-backed API.

We start `consilium-api` in a background subprocess on a free port, set
env vars so the CLI picks them up via `load_config`, then invoke the CLI
as a subprocess and check exit code + stdout + side effects.

Gated by @pytest.mark.integration so a plain `pytest` run doesn't need a
live API.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest


def _pick_free_port() -> int:
    """Ask the OS for an unused TCP port, then release it. Tiny race but fine."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def live_api(tmp_path, monkeypatch):
    """Spin up a real consilium-api uvicorn subprocess on a random port.

    Yields (base_url, token). Shuts down on teardown."""
    port = _pick_free_port()
    token = "integration-token-xyz"

    env = os.environ.copy()
    env.update(
        {
            "CONSILIUM_API_TOKEN": token,
            "CONSILIUM_DATA_DIR": str(tmp_path / "data"),
            "ANTHROPIC_API_KEY": "sk-fake",
            "OPENROUTER_API_KEY": "sk-fake",
            "PERPLEXITY_API_KEY": "pplx-fake",
        }
    )

    proc = subprocess.Popen(
        ["consilium-api", "--port", str(port), "--host", "127.0.0.1"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for the server to accept connections (max 5s)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 5
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(
                f"{base_url}/templates",
                headers={"Authorization": f"Bearer {token}"},
                timeout=0.5,
            )
            if r.status_code == 200:
                break
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(0.1)
    else:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=2)
        raise RuntimeError(
            f"API didn't come up on {base_url}: {last_err}\n"
            f"stdout: {stdout.decode()[:500]}\n"
            f"stderr: {stderr.decode()[:500]}"
        )

    yield base_url, token

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def _cli(
    args: list[str],
    *,
    base_url: str,
    token: str,
    extra_env: dict | None = None,
    input_text: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "CONSILIUM_API_BASE": base_url,
            "CONSILIUM_API_TOKEN": token,
            "CONSILIUM_CLIENT_CONFIG": "/nonexistent.yaml",
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["consilium"] + args,
        env=env,
        capture_output=True,
        text=True,
        input=input_text,
        cwd=str(cwd) if cwd else None,
        timeout=20,
    )


@pytest.mark.integration
def test_cli_version_does_not_need_api():
    r = subprocess.run(
        ["consilium", "--version"], capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "consilium" in r.stdout.lower()


@pytest.mark.integration
def test_cli_templates_list_against_live_api(live_api):
    base_url, token = live_api
    r = _cli(["templates", "list"], base_url=base_url, token=token)
    assert r.returncode == 0, f"stderr: {r.stderr}"
    # product_concept template ships with the repo
    assert "product_concept" in r.stdout or "quick_check" in r.stdout


@pytest.mark.integration
def test_cli_jobs_list_empty(live_api):
    base_url, token = live_api
    r = _cli(["jobs", "list"], base_url=base_url, token=token)
    assert r.returncode == 0, f"stderr: {r.stderr}"


@pytest.mark.integration
def test_cli_bad_token_shows_auth_error(live_api, tmp_path):
    base_url, _token = live_api
    r = _cli(
        ["templates", "list"],
        base_url=base_url,
        token="obviously-wrong-token",
    )
    # Bad token → AuthError → non-zero exit (CLI prints error, no template list)
    # Exact exit code depends on what path the client takes.
    assert r.returncode != 0 or "unauthorized" in (r.stdout + r.stderr).lower()


@pytest.mark.integration
def test_cli_preview_with_real_preview_endpoint(live_api):
    base_url, token = live_api
    r = _cli(
        ["debate", "--preview", "-t", "quick_check", "тестовая тема"],
        base_url=base_url,
        token=token,
    )
    assert r.returncode == 0, f"stderr: {r.stderr}\nstdout: {r.stdout}"
    assert "Preview" in r.stdout or "preview" in r.stdout.lower()
    assert "$" in r.stdout  # cost estimate printed


@pytest.mark.integration
def test_cli_archive_get_nonexistent_returns_error(live_api):
    base_url, token = live_api
    r = _cli(
        ["archive", "show", "99999"],
        base_url=base_url,
        token=token,
    )
    assert r.returncode == 2
    assert "99999" in r.stdout + r.stderr or "not" in (r.stdout + r.stderr).lower()


@pytest.mark.integration
def test_cli_packs_create_roundtrip(live_api, tmp_path):
    base_url, token = live_api
    brief = tmp_path / "brief.md"
    brief.write_text("# Test\ncontent", encoding="utf-8")

    name = "integration_pack"
    # create
    r = _cli(
        ["packs", "create", name, str(brief)],
        base_url=base_url,
        token=token,
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
    # show
    r = _cli(
        ["packs", "show", name], base_url=base_url, token=token
    )
    assert r.returncode == 0
    assert name in r.stdout or "brief.md" in r.stdout
    # delete
    r = _cli(
        ["packs", "delete", name], base_url=base_url, token=token
    )
    assert r.returncode == 0
    assert "удал" in r.stdout.lower()


@pytest.mark.integration
def test_cli_help_is_self_contained():
    """No network, no API needed — help text must render standalone."""
    r = subprocess.run(
        ["consilium", "--help"], capture_output=True, text=True
    )
    assert r.returncode == 0
    for sub in ("debate", "jobs", "archive", "packs", "budget", "templates"):
        assert sub in r.stdout

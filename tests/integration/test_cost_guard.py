"""End-to-end guard test — tight limits must block run_debate BEFORE any API
call happens. Runs as a subprocess so we see the real exit code and stderr.

Important: this test uses NO real API — it proves the guard works without
incurring any provider cost. That's why it isn't marked with the `integration`
marker (which gates on real keys). Kept under tests/integration/ for shape
consistency with other end-to-end tests.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
RUN_DEBATE = PROJECT_ROOT / "scripts" / "run_debate.py"


def _run(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUN_DEBATE), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        timeout=60,
    )


def _env_with_fake_keys(tmp_path: Path, limits_text: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["CONSILIUM_DATA_DIR"] = str(tmp_path)
    # Always supply fake keys — guard must block BEFORE any API call so these
    # never actually get used. Overwrite unconditionally (parent env may have
    # empty strings left over from `.env.example`).
    env["ANTHROPIC_API_KEY"] = "sk-fake-anthropic"
    env["OPENROUTER_API_KEY"] = "sk-fake-openrouter"
    env["PERPLEXITY_API_KEY"] = "pplx-fake"
    if limits_text is not None:
        limits_file = tmp_path / "limits.yaml"
        limits_file.write_text(limits_text, encoding="utf-8")
        env["CONSILIUM_LIMITS_FILE"] = str(limits_file)
    return env


def test_per_job_cap_blocks_before_api_call(tmp_path):
    """Limit per_job=$0.01 → quick_check (~$0.10) blocked with exit code 3."""
    env = _env_with_fake_keys(
        tmp_path,
        limits_text="max_cost_per_job_usd: 0.01\n",
    )
    result = _run(
        [
            "--yes",
            "--template",
            "quick_check",
            "--no-archive",
            "тестовая тема для пределов",
        ],
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 3, (
        f"Expected exit 3 (blocked); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    assert "per_job" in result.stderr.lower() or "per-job" in result.stderr.lower()
    # No local md files should exist (no debate actually ran)
    md_files = list((tmp_path / "consilium").rglob("*.md"))
    assert md_files == []


def test_rounds_too_high_fails_validation(tmp_path):
    """max_rounds=1 in limits → the default product_concept (rounds=2) fails
    structural validation with exit code 2 before anything else."""
    env = _env_with_fake_keys(tmp_path, limits_text="max_rounds: 1\n")
    result = _run(
        [
            "--yes",
            "--template",
            "product_concept",
            "--no-archive",
            "тема",
        ],
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 2, (
        f"Expected exit 2 (structural); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    assert "rounds" in result.stderr.lower()


def test_force_bypasses_per_job_cap_but_exits_on_fake_api(tmp_path):
    """With --force the guard lets the debate through; it then fails at the
    first provider call because of fake keys. Exit code will be non-zero due
    to the HTTP failure, NOT 2/3 from the guard."""
    env = _env_with_fake_keys(
        tmp_path, limits_text="max_cost_per_job_usd: 0.01\n"
    )
    result = _run(
        [
            "--yes",
            "--force",
            "--template",
            "quick_check",
            "--no-archive",
            "тестовая тема",
        ],
        env=env,
        cwd=tmp_path,
    )
    # Either a non-zero exit from API error, or timeout killed it —
    # both prove the guard WAS bypassed (otherwise we'd see exit 3).
    assert result.returncode != 3, (
        f"Guard did not bypass on --force: stderr={result.stderr}"
    )

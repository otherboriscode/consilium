"""
`ClientConfig` — resolves `api_base` + `token` from env or a YAML file at
`~/.config/consilium/client.yaml`.

Priority: env vars first (for CI / explicit overrides), YAML file second,
error if neither has a value. Keeping this dumb-simple — no multi-profile
support, no OAuth, no token refresh.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ClientConfig:
    api_base: str
    token: str
    timeout_seconds: float = 30.0


def _default_config_path() -> Path:
    env = os.environ.get("CONSILIUM_CLIENT_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".config" / "consilium" / "client.yaml"


def load_config(*, path: Path | None = None) -> ClientConfig:
    """Load client config. Env wins over file; raises if neither is complete."""
    p = path or _default_config_path()
    data: dict = {}
    if p.is_file():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    api_base = os.environ.get("CONSILIUM_API_BASE") or data.get("api_base")
    token = os.environ.get("CONSILIUM_API_TOKEN") or data.get("token")
    timeout_raw = os.environ.get(
        "CONSILIUM_API_TIMEOUT", data.get("timeout_seconds", 30)
    )
    timeout = float(timeout_raw)

    if not api_base or not token:
        raise ValueError(
            f"Client config incomplete. Set CONSILIUM_API_BASE and "
            f"CONSILIUM_API_TOKEN env vars, or provide {p} with api_base "
            f"and token fields."
        )
    return ClientConfig(
        api_base=str(api_base), token=str(token), timeout_seconds=timeout
    )

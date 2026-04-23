"""
Shared async client for the Consilium HTTPS API.

Used by the Telegram bot (`consilium_server.bot.*`), MCP server
(`consilium_mcp.*`), and CLI (`consilium_cli.*`). Single source of
truth for the wire contract.
"""
from __future__ import annotations

from consilium_client.client import (
    ConsiliumClient,
    JobStatus,
    ParticipantPreviewRow,
    PreviewResult,
    SubmitResult,
)
from consilium_client.config import ClientConfig, load_config
from consilium_client.errors import (
    AuthError,
    ConsiliumClientError,
    CostDenied,
    JobNotFound,
    NetworkError,
    RateLimited,
)

__all__ = [
    "ConsiliumClient",
    "ClientConfig",
    "load_config",
    "SubmitResult",
    "JobStatus",
    "PreviewResult",
    "ParticipantPreviewRow",
    "ConsiliumClientError",
    "AuthError",
    "JobNotFound",
    "CostDenied",
    "RateLimited",
    "NetworkError",
]

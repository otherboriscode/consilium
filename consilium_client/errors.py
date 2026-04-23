"""
Typed exceptions surfaced by `ConsiliumClient`.

These cover the interesting failure modes from the Consilium API:
 - 401 → AuthError
 - 402 → CostDenied (carries violations so a caller can render a prompt)
 - 404 → JobNotFound (also used for unknown packs/archive entries)
 - 429 → RateLimited
 - network/timeouts → NetworkError

Everything else is surfaced as `ConsiliumClientError` with the status code.
"""
from __future__ import annotations


class ConsiliumClientError(Exception):
    """Base class for all typed client failures."""


class AuthError(ConsiliumClientError):
    """401 — bad or missing token."""


class JobNotFound(ConsiliumClientError):
    """404 — unknown job / pack / archive entry."""


class CostDenied(ConsiliumClientError):
    """402 — cost guard refused the submission. Carries violation details
    so the client can show the user what tripped and offer --force."""

    def __init__(
        self,
        *,
        violations: list[str],
        messages: list[str],
        estimate: float,
    ) -> None:
        self.violations = violations
        self.messages = messages
        self.estimate = estimate
        super().__init__(f"Cost guard denied: {violations}")


class RateLimited(ConsiliumClientError):
    """429 — server is busy (concurrency cap or rate limit)."""


class NetworkError(ConsiliumClientError):
    """Connection/timeout failure — couldn't reach the API at all."""

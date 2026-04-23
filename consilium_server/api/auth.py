"""
Bearer-token authentication dependency.

Token is read from `CONSILIUM_API_TOKEN` env var on every request (cheap)
so the running server can be rotated without a restart. Missing token →
500 (fail-safe: if Boris forgot to set it, don't silently accept anything).
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status


def _expected_token() -> str:
    tok = os.environ.get("CONSILIUM_API_TOKEN")
    if not tok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CONSILIUM_API_TOKEN not configured on server",
        )
    return tok


async def require_bearer(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization is None:
        raise HTTPException(
            status_code=401, detail="Missing Authorization header"
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Expected 'Bearer <token>'"
        )
    token = authorization[len("Bearer ") :].strip()
    expected = _expected_token()
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid token")


AuthDep = Annotated[None, Depends(require_bearer)]

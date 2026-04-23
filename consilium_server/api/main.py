"""
Consilium HTTPS API — FastAPI-based single entry point for Telegram bot
(Phase 7), MCP server (Phase 8), and any future clients. Bearer-token auth,
SSE for progress streaming, background tasks for debates.
"""
from __future__ import annotations

from fastapi import FastAPI

from consilium_server.api.auth import AuthDep

app = FastAPI(
    title="Consilium",
    version="0.6.0",
    description="Multi-LLM council for developer product concept work",
)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Stub: real routers get registered in Tasks 6.4+. Kept minimal here so the
# auth dependency has a protected endpoint to gate.
@app.get("/jobs", include_in_schema=False)
async def list_jobs_stub(_: AuthDep) -> list[dict]:
    return []


def main() -> None:
    """Entry point for `consilium-api` CLI."""
    import uvicorn

    uvicorn.run(
        "consilium_server.api.main:app",
        host="127.0.0.1",
        port=8421,
        reload=False,
    )


if __name__ == "__main__":
    main()

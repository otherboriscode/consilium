"""
Consilium HTTPS API — FastAPI-based single entry point for Telegram bot
(Phase 7), MCP server (Phase 8), and any future clients. Bearer-token auth,
SSE for progress streaming, background tasks for debates.
"""
from __future__ import annotations

import logging
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from consilium_server.api.routes import archive as archive_router
from consilium_server.api.routes import budget as budget_router
from consilium_server.api.routes import jobs as jobs_router
from consilium_server.api.routes import packs as packs_router

logger = logging.getLogger("consilium.api")

app = FastAPI(
    title="Consilium",
    version="0.7.0",  # bumped for Phase 7
    description="Multi-LLM council for developer product concept work",
)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds the cap.

    We check only the header — not streaming body size — because this is a
    single-user tool where the client (Telegram bot / CLI) controls its own
    payloads. Catches accidents like a 200 MB pack upload before we allocate.
    """

    def __init__(self, app, max_body_bytes: int = 10 * 1024 * 1024) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                size = int(cl)
            except ValueError:
                size = 0
            if size > self.max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Body exceeds {self.max_body_bytes} bytes"
                    },
                )
        return await call_next(request)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Log each request with a short request-id that echoes back to the client."""
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())[:8]
    t0 = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "req %s %s %s -> %d (%.0fms)",
        rid,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    response.headers["x-request-id"] = rid
    return response


app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=10 * 1024 * 1024)

# CORS is off by default; enable with `CONSILIUM_CORS_ORIGINS=a.com,b.com`.
_cors = os.environ.get("CONSILIUM_CORS_ORIGINS", "").strip()
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(jobs_router.router)
app.include_router(archive_router.router)
app.include_router(budget_router.router)
app.include_router(packs_router.router)


def main() -> None:
    """Entry point for `consilium-api` CLI."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="consilium-api")
    parser.add_argument(
        "--host",
        default=os.environ.get("CONSILIUM_API_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1; set CONSILIUM_API_HOST to override)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CONSILIUM_API_PORT", "8421")),
        help="Bind port (default: 8421)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload (dev only)",
    )
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    uvicorn.run(
        "consilium_server.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

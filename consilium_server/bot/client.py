"""
Async wrapper around the Consilium HTTPS API. Used by the Telegram bot
(Phase 7) and any other future clients (MCP in Phase 8).

Exposes typed errors for the interesting failure modes:
 - AuthError   — 401 (bad or missing token)
 - JobNotFound — 404 (unknown job / pack / archive entry)
 - CostDenied  — 402 (cost-guard rejected submission; carries violations)
 - ConsiliumClientError — base class for everything else

The rest are surfaced as `httpx.HTTPStatusError`.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx


class ConsiliumClientError(Exception):
    pass


class AuthError(ConsiliumClientError):
    pass


class JobNotFound(ConsiliumClientError):
    pass


class CostDenied(ConsiliumClientError):
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
    pass


@dataclass
class SubmitResult:
    job_id: int
    status: str
    estimated_cost_usd: float
    estimated_duration_seconds: float
    warnings: list[str]


@dataclass
class JobStatus:
    job_id: int
    status: str
    rounds_completed: int
    rounds_total: int
    current_cost_usd: float
    estimated_cost_usd: float
    template: str
    topic: str
    project: str | None
    error: str | None


@dataclass
class PreviewResult:
    estimated_cost_usd: float
    estimated_duration_seconds: float
    warnings: list[str]


class ConsiliumClient:
    """Context-manager-based async client. Always use `async with`."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ConsiliumClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "ConsiliumClient must be used as async context manager"
            )
        return self._client

    @staticmethod
    def _raise_for(response: httpx.Response) -> None:
        """Translate HTTP errors into typed exceptions (or raise_for_status)."""
        if response.status_code == 401:
            try:
                detail = response.json().get("detail", "unauthorized")
            except Exception:
                detail = "unauthorized"
            raise AuthError(str(detail))
        if response.status_code == 404:
            try:
                detail = response.json().get("detail", "not found")
            except Exception:
                detail = "not found"
            raise JobNotFound(str(detail))
        if response.status_code == 402:
            try:
                d = response.json().get("detail", {})
            except Exception:
                d = {}
            raise CostDenied(
                violations=d.get("violations", []) if isinstance(d, dict) else [],
                messages=d.get("messages", []) if isinstance(d, dict) else [],
                estimate=d.get("estimated_cost_usd", 0.0)
                if isinstance(d, dict)
                else 0.0,
            )
        if response.status_code == 429:
            try:
                detail = response.json().get("detail", "rate limited")
            except Exception:
                detail = "rate limited"
            raise RateLimited(str(detail))
        response.raise_for_status()

    # ----- jobs -------------------------------------------------------

    async def submit_job(
        self,
        *,
        topic: str,
        template: str,
        pack: str | None = None,
        context_block: str | None = None,
        project: str | None = None,
        force: bool = False,
        rounds: int | None = None,
    ) -> SubmitResult:
        body: dict = {
            "topic": topic,
            "template": template,
            "pack": pack,
            "context_block": context_block,
            "project": project,
            "force": force,
            "rounds": rounds,
        }
        # Drop None fields so pydantic doesn't complain about nulls in optional
        # fields that have explicit defaults.
        body = {k: v for k, v in body.items() if v is not None}
        r = await self._c().post("/jobs", json=body)
        self._raise_for(r)
        return SubmitResult(**r.json())

    async def preview_job(
        self,
        *,
        topic: str,
        template: str,
        pack: str | None = None,
        context_block: str | None = None,
        project: str | None = None,
        rounds: int | None = None,
    ) -> PreviewResult:
        """Dry-run submission: run structural validation and cost check,
        return estimate without starting anything. 402 still raises CostDenied."""
        body: dict = {
            "topic": topic,
            "template": template,
            "pack": pack,
            "context_block": context_block,
            "project": project,
            "rounds": rounds,
        }
        body = {k: v for k, v in body.items() if v is not None}
        r = await self._c().post("/preview", json=body)
        self._raise_for(r)
        return PreviewResult(**r.json())

    async def get_status(self, job_id: int) -> JobStatus:
        r = await self._c().get(f"/jobs/{job_id}")
        self._raise_for(r)
        d = r.json()
        return JobStatus(
            job_id=d["job_id"],
            status=d["status"],
            rounds_completed=d["rounds_completed"],
            rounds_total=d["rounds_total"],
            current_cost_usd=d["current_cost_usd"],
            estimated_cost_usd=d["estimated_cost_usd"],
            template=d["template"],
            topic=d.get("topic", ""),
            project=d.get("project"),
            error=d.get("error"),
        )

    async def list_jobs(
        self, *, project: str | None = None, limit: int = 20
    ) -> list[dict]:
        params = {"limit": limit}
        if project is not None:
            params["project"] = project  # type: ignore[assignment]
        r = await self._c().get("/jobs", params=params)
        self._raise_for(r)
        return r.json()

    async def cancel_job(self, job_id: int) -> None:
        r = await self._c().post(f"/jobs/{job_id}/cancel")
        self._raise_for(r)

    async def stream_events(self, job_id: int) -> AsyncIterator[dict]:
        """Subscribe to SSE. Yields a dict per event. Terminates when the
        server closes the stream (job finished) or on keepalive-only for 5+ min."""
        async with self._c().stream(
            "GET", f"/jobs/{job_id}/events"
        ) as response:
            if response.status_code != 200:
                # Can't yield then raise — convert body to an exception first.
                body = await response.aread()
                fake = httpx.Response(
                    response.status_code, content=body, request=response.request
                )
                self._raise_for(fake)
                return
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    payload = line[len("data: ") :]
                    if payload:
                        try:
                            yield json.loads(payload)
                        except json.JSONDecodeError:
                            continue

    # ----- archive ----------------------------------------------------

    async def get_archive_json(self, job_id: int) -> dict:
        r = await self._c().get(f"/archive/{job_id}")
        self._raise_for(r)
        return r.json()

    async def get_archive_md(self, job_id: int) -> str:
        r = await self._c().get(f"/archive/{job_id}/md")
        self._raise_for(r)
        return r.text

    async def search_archive(
        self, query: str, *, limit: int = 20
    ) -> list[dict]:
        r = await self._c().get(
            "/archive/search", params={"q": query, "limit": limit}
        )
        self._raise_for(r)
        return r.json()

    # ----- budget -----------------------------------------------------

    async def get_usage(self) -> dict:
        r = await self._c().get("/budget/usage")
        self._raise_for(r)
        return r.json()

    async def get_limits(self) -> dict:
        r = await self._c().get("/budget/limits")
        self._raise_for(r)
        return r.json()

    async def get_daily_summary(self) -> str:
        r = await self._c().get("/budget/daily")
        self._raise_for(r)
        return r.json()["summary_markdown"]

    # ----- templates --------------------------------------------------

    async def list_templates(self) -> list[str]:
        r = await self._c().get("/templates")
        self._raise_for(r)
        return r.json()

    async def show_template(self, name: str) -> dict:
        r = await self._c().get(f"/templates/{name}")
        self._raise_for(r)
        return r.json()

    # ----- packs ------------------------------------------------------

    async def list_packs(self) -> list[str]:
        r = await self._c().get("/packs")
        self._raise_for(r)
        return r.json()

    async def show_pack(self, name: str) -> dict:
        r = await self._c().get(f"/packs/{name}")
        self._raise_for(r)
        return r.json()

    async def create_pack(
        self, name: str, files: list[tuple[str, bytes]]
    ) -> dict:
        """`files`: list of (filename, content_bytes)."""
        multipart = [
            ("files", (fname, content))
            for fname, content in files
        ]
        r = await self._c().post(f"/packs/{name}", files=multipart)
        self._raise_for(r)
        return r.json()

    async def delete_pack(self, name: str) -> None:
        r = await self._c().delete(f"/packs/{name}")
        self._raise_for(r)

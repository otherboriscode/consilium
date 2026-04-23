"""
Async wrapper around the Consilium HTTPS API.

Shared by all three client surfaces:
  - Telegram bot (`consilium_server.bot.*`)
  - MCP server (`consilium_mcp.*`)
  - CLI (`consilium_cli.*`)

Must be used as an async context manager. Typed errors for the interesting
failure modes live in `consilium_client.errors`.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from consilium_client.errors import (
    AuthError,
    ConsiliumClientError,
    CostDenied,
    JobNotFound,
    NetworkError,
    RateLimited,
)


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
class ParticipantPreviewRow:
    role: str
    model: str
    mode: str  # "fast" | "deep"
    fit: str  # "full" | "summary" | "exclude"
    estimated_cost_usd: float


@dataclass
class PreviewResult:
    estimated_cost_usd: float
    estimated_duration_seconds: float
    context_tokens: int
    template: str
    rounds: int
    participants: list[ParticipantPreviewRow]
    judge_model: str
    allowed: bool
    violations: list[str]
    violation_messages: list[str]
    warnings: list[str]


class ConsiliumClient:
    """Context-manager-based async client. Always use `async with`."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport  # lets tests plug in ASGITransport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ConsiliumClient:
        kwargs: dict = {
            "base_url": self._base_url,
            "headers": {"Authorization": f"Bearer {self._token}"},
            "timeout": self._timeout,
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
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
        """Translate HTTP errors into typed exceptions."""
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
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ConsiliumClientError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            ) from e

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Wrap httpx calls so connect/timeout errors become `NetworkError`."""
        try:
            r = await self._c().request(method, url, **kwargs)
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.NetworkError,
        ) as e:
            raise NetworkError(str(e)) from e
        self._raise_for(r)
        return r

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
        body = {k: v for k, v in body.items() if v is not None}
        r = await self._request("POST", "/jobs", json=body)
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
        force: bool = False,
    ) -> PreviewResult:
        """Dry-run submission — run validation + cost check, return rich
        estimate (per-participant fit, context_tokens, etc.) without
        starting anything.

        Cost-cap violations come back as `allowed=False` in the body, not
        as 402. 404 (unknown template/pack) and 422 (structural) still
        raise as with `/jobs`.
        """
        body: dict = {
            "topic": topic,
            "template": template,
            "pack": pack,
            "context_block": context_block,
            "project": project,
            "rounds": rounds,
            "force": force,
        }
        body = {k: v for k, v in body.items() if v is not None}
        r = await self._request("POST", "/preview", json=body)
        d = r.json()
        return PreviewResult(
            estimated_cost_usd=d["estimated_cost_usd"],
            estimated_duration_seconds=d["estimated_duration_seconds"],
            context_tokens=d.get("context_tokens", 0),
            template=d.get("template", template),
            rounds=d.get("rounds", 0),
            participants=[
                ParticipantPreviewRow(**p) for p in d.get("participants", [])
            ],
            judge_model=d.get("judge_model", ""),
            allowed=d.get("allowed", True),
            violations=d.get("violations", []),
            violation_messages=d.get("violation_messages", []),
            warnings=d.get("warnings", []),
        )

    async def get_status(self, job_id: int) -> JobStatus:
        r = await self._request("GET", f"/jobs/{job_id}")
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
        params: dict = {"limit": limit}
        if project is not None:
            params["project"] = project
        r = await self._request("GET", "/jobs", params=params)
        return r.json()

    async def cancel_job(self, job_id: int) -> None:
        await self._request("POST", f"/jobs/{job_id}/cancel")

    async def stream_events(self, job_id: int) -> AsyncIterator[dict]:
        """Subscribe to SSE. Yields a dict per event. Terminates when the
        server closes the stream."""
        try:
            async with self._c().stream(
                "GET", f"/jobs/{job_id}/events"
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    fake = httpx.Response(
                        response.status_code,
                        content=body,
                        request=response.request,
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
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.NetworkError,
        ) as e:
            raise NetworkError(str(e)) from e

    # ----- archive ----------------------------------------------------

    async def get_archive_json(self, job_id: int) -> dict:
        r = await self._request("GET", f"/archive/{job_id}")
        return r.json()

    async def get_archive_md(self, job_id: int) -> str:
        r = await self._request("GET", f"/archive/{job_id}/md")
        return r.text

    async def search_archive(
        self, query: str, *, limit: int = 20
    ) -> list[dict]:
        r = await self._request(
            "GET", "/archive/search", params={"q": query, "limit": limit}
        )
        return r.json()

    # ----- budget -----------------------------------------------------

    async def get_usage(self) -> dict:
        r = await self._request("GET", "/budget/usage")
        return r.json()

    async def get_limits(self) -> dict:
        r = await self._request("GET", "/budget/limits")
        return r.json()

    async def get_daily_summary(self) -> str:
        r = await self._request("GET", "/budget/daily")
        return r.json()["summary_markdown"]

    # ----- templates --------------------------------------------------

    async def list_templates(self) -> list[str]:
        r = await self._request("GET", "/templates")
        return r.json()

    async def show_template(self, name: str) -> dict:
        r = await self._request("GET", f"/templates/{name}")
        return r.json()

    # ----- packs ------------------------------------------------------

    async def list_packs(self) -> list[str]:
        r = await self._request("GET", "/packs")
        return r.json()

    async def show_pack(self, name: str) -> dict:
        r = await self._request("GET", f"/packs/{name}")
        return r.json()

    async def create_pack(
        self, name: str, files: list[tuple[str, bytes]]
    ) -> dict:
        """`files`: list of (filename, content_bytes)."""
        multipart = [("files", (fname, content)) for fname, content in files]
        r = await self._request("POST", f"/packs/{name}", files=multipart)
        return r.json()

    async def delete_pack(self, name: str) -> None:
        await self._request("DELETE", f"/packs/{name}")

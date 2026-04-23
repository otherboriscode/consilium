"""
Archive MCP tools.

  consilium_archive_search(query, limit?) → list of jobs
  consilium_archive_get(job_id, save_to?) → local markdown path + size
  consilium_archive_stats(group_by?)       → aggregates
  consilium_archive_roi()                  → ROI rows
"""
from __future__ import annotations

from pathlib import Path

from consilium_client import JobNotFound
from consilium_mcp.registry import Registry, ToolSpec


def register(registry: Registry, *, client_factory) -> None:
    async def _search(args: dict) -> list[dict]:
        async with client_factory() as client:
            return await client.search_archive(
                args["query"], limit=int(args.get("limit", 20))
            )

    async def _get(args: dict) -> dict:
        job_id = int(args["job_id"])
        save_to = args.get("save_to") or f"./consilium/{job_id:04d}.md"
        async with client_factory() as client:
            try:
                md = await client.get_archive_md(job_id)
            except JobNotFound as e:
                return {"error": "not_found", "message": str(e)}
        out = Path(save_to).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        return {
            "md_path": str(out),
            "bytes": len(md.encode("utf-8")),
        }

    async def _stats(args: dict) -> list[dict]:
        group_by = args.get("group_by", "model")
        async with client_factory() as client:
            return await client.archive_stats(group_by=group_by)

    async def _roi(_args: dict) -> list[dict]:
        async with client_factory() as client:
            return await client.archive_roi()

    registry.add(
        ToolSpec(
            name="consilium_archive_search",
            description="FTS search across archived debates.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
            handler=_search,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_archive_get",
            description="Download an archived debate's markdown transcript.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "save_to": {
                        "type": "string",
                        "description": (
                            "Local path. Defaults to ./consilium/{id}.md"
                        ),
                    },
                },
                "required": ["job_id"],
            },
            handler=_get,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_archive_stats",
            description="Aggregate stats over archive (by model/template/project).",
            input_schema={
                "type": "object",
                "properties": {
                    "group_by": {
                        "type": "string",
                        "enum": ["model", "template", "project"],
                        "default": "model",
                    },
                },
            },
            handler=_stats,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_archive_roi",
            description="ROI rows — cost vs conclusions depth.",
            input_schema={"type": "object", "properties": {}},
            handler=_roi,
        )
    )

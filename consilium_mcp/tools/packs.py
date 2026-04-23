"""
Packs MCP tools.

  consilium_packs_list()
  consilium_pack_show(name)
  consilium_pack_create(name, file_paths[])
  consilium_pack_delete(name)
"""
from __future__ import annotations

from pathlib import Path

from consilium_client import JobNotFound
from consilium_mcp.registry import Registry, ToolSpec


def register(registry: Registry, *, client_factory) -> None:
    async def _list(_args: dict, **_) -> list[str]:
        async with client_factory() as client:
            return await client.list_packs()

    async def _show(args: dict, **_) -> dict:
        async with client_factory() as client:
            try:
                return await client.show_pack(args["name"])
            except JobNotFound as e:
                return {"error": "not_found", "message": str(e)}

    async def _create(args: dict, **_) -> dict:
        name = args["name"]
        file_paths = args["file_paths"]
        payload: list[tuple[str, bytes]] = []
        for p_str in file_paths:
            p = Path(p_str).expanduser()
            if not p.is_file():
                return {
                    "error": "not_a_file",
                    "message": f"Not a file: {p}",
                }
            payload.append((p.name, p.read_bytes()))
        async with client_factory() as client:
            return await client.create_pack(name, files=payload)

    async def _delete(args: dict, **_) -> dict:
        async with client_factory() as client:
            try:
                await client.delete_pack(args["name"])
            except JobNotFound as e:
                return {"error": "not_found", "message": str(e)}
        return {"deleted": True, "name": args["name"]}

    registry.add(
        ToolSpec(
            name="consilium_packs_list",
            description="List all named context packs.",
            input_schema={"type": "object", "properties": {}},
            handler=_list,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_pack_show",
            description="Details of one pack: file list, tokens, staleness.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=_show,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_pack_create",
            description=(
                "Create (or overwrite) a named pack from local files. "
                "file_paths are absolute paths on the machine running MCP."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["name", "file_paths"],
            },
            handler=_create,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_pack_delete",
            description="Delete a named pack.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=_delete,
        )
    )

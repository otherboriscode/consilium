"""
Templates MCP tools.

  consilium_templates_list()
  consilium_template_show(name)
"""
from __future__ import annotations

from consilium_client import JobNotFound
from consilium_mcp.registry import Registry, ToolSpec


def register(registry: Registry, *, client_factory) -> None:
    async def _list(_args: dict) -> list[str]:
        async with client_factory() as client:
            return await client.list_templates()

    async def _show(args: dict) -> dict:
        async with client_factory() as client:
            try:
                return await client.show_template(args["name"])
            except JobNotFound as e:
                return {"error": "not_found", "message": str(e)}

    registry.add(
        ToolSpec(
            name="consilium_templates_list",
            description="List available YAML debate templates.",
            input_schema={"type": "object", "properties": {}},
            handler=_list,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_template_show",
            description=(
                "Show template details — participants, roles, models, judge."
            ),
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=_show,
        )
    )

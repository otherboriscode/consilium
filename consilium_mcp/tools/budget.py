"""
Budget MCP tools.

  consilium_budget_usage()
  consilium_budget_limits()
  consilium_budget_daily()     # markdown string
  consilium_budget_alerts()
"""
from __future__ import annotations

from consilium_mcp.registry import Registry, ToolSpec


def register(registry: Registry, *, client_factory) -> None:
    async def _usage(_args: dict) -> dict:
        async with client_factory() as client:
            return await client.get_usage()

    async def _limits(_args: dict) -> dict:
        async with client_factory() as client:
            return await client.get_limits()

    async def _daily(_args: dict) -> str:
        async with client_factory() as client:
            return await client.get_daily_summary()

    async def _alerts(_args: dict) -> dict:
        async with client_factory() as client:
            return await client.get_alerts()

    registry.add(
        ToolSpec(
            name="consilium_budget_usage",
            description="Current spend: today + this month, broken down by model.",
            input_schema={"type": "object", "properties": {}},
            handler=_usage,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_budget_limits",
            description="Configured spend limits (per-job, per-day, per-month).",
            input_schema={"type": "object", "properties": {}},
            handler=_limits,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_budget_daily",
            description="Markdown summary of today's activity and cost.",
            input_schema={"type": "object", "properties": {}},
            handler=_daily,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_budget_alerts",
            description="Which 50/80/95% budget thresholds are currently fired.",
            input_schema={"type": "object", "properties": {}},
            handler=_alerts,
        )
    )

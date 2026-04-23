"""
`consilium-mcp` entry point.

Runs the stdio MCP server. Config is read from env vars
`CONSILIUM_API_BASE` and `CONSILIUM_API_TOKEN` (or from
`~/.config/consilium/client.yaml` — see `consilium_client.load_config`).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from consilium_mcp.server import run_stdio


def main() -> None:
    log_level = os.environ.get("CONSILIUM_MCP_LOG_LEVEL", "INFO")
    # Logs to stderr — stdout is the MCP stdio channel and must stay pristine.
    logging.basicConfig(
        level=log_level,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()

# CLAUDE.md — project-local rules for Claude sessions in this repo

## Documentation discipline (HARD RULE)

**Every new feature, command, endpoint, template, or config knob must be
added to ALL relevant documentation in the same commit, not "later":**

- `README.md` — high-level surface: one-line mention + link to details
- `docs/INSTALL.md` — user-facing: how to invoke, typical usage,
  decision rules for when to use vs. alternatives
- `docs/OPS.md` — operational: if the change affects deployment, env
  vars, systemd units, backup, monitoring, or troubleshooting — update
  the relevant section. If purely end-user (new template, new CLI
  subcommand) — mention in "Day-to-day" / "Useful one-liners" if it's
  plausibly useful for the operator, otherwise skip.
- `docs/plans/*.md` — treat as historical artifacts; don't rewrite past
  plans but reference them when the new work extends their scope.

Don't assume "the user-facing docs are enough." OPS.md may need updating
too (e.g. a new template changes the smoke-test list; a new endpoint
changes the troubleshooting matrix). Think explicitly: *which reader
needs to know about this change?*

When in doubt — update. A line mentioning a feature in the wrong
place is recoverable; a feature invisible in docs is not.

## Where things live

- `consilium/` — pure core: providers, orchestrator, templates, archive,
  cost, limits. No HTTP, no aiogram, no MCP.
- `consilium_server/api/` — FastAPI wrapper over the core.
- `consilium_server/bot/` — aiogram Telegram bot (thin client over API).
- `consilium_client/` — shared async client (used by bot, CLI, MCP).
- `consilium_cli/` — `consilium` command-line tool.
- `consilium_mcp/` — MCP server for Claude Code integration.
- `templates_default/*.yaml` — shipped debate templates.
- `deploy/` — systemd units, nginx config, install script, backup script.
- `docs/` — INSTALL, OPS, plan history.
- `tests/{bot,client,cli,mcp,server,integration,…}` — by layer.

## Style

- Bilingual: user-facing copy can be Russian (Boris's native), code
  comments and docstrings English.
- No emoji in code/docs unless the user explicitly asks.
- Never add `__pycache__`, `.pyc`, or `.env` to commits.
- Follow existing line-width (ruff says 100).

## Testing

- `pytest -q` runs fast unit suite.
- `pytest -m integration` requires live API + provider keys.
- Don't add tests that hit real LLMs without the `@pytest.mark.integration`
  marker — CI must stay fast and deterministic.

## Deployment

- VPS: `89.167.73.98` (see `docs/OPS.md`).
- Update flow: `git pull` on VPS → `pip install -e ".[api,bot]"` →
  `systemctl restart consilium-api consilium-bot`.
- Templates load at submit time, no restart needed for new `.yaml` files.

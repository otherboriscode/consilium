# Consilium — Installation & Integration Guide

Three entry points share one engine:

- **Telegram bot** (Phase 7) — remote access from phone
- **MCP in Claude Code** (Phase 8) — native integration for project work
- **CLI** (Phase 8) — universal fallback, cron-compatible

All three talk to the same local `consilium-api` HTTPS server, which in
turn orchestrates LLM providers.

---

## 1. Install the API server

```bash
cd ~/projects/consilium
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[api,cli,mcp,bot,dev]"

# Provider API keys (store in ~/.zshrc, direnv, or 1Password CLI — NOT git)
export ANTHROPIC_API_KEY=sk-ant-...
export OPENROUTER_API_KEY=sk-or-...
export PERPLEXITY_API_KEY=pplx-...

# Local API bearer token — generate a random one once
export CONSILIUM_API_TOKEN=$(openssl rand -hex 32)
echo "CONSILIUM_API_TOKEN=$CONSILIUM_API_TOKEN"  # save this

# Start the API on localhost
consilium-api --port 8421
```

Leave this running in its own terminal (or wrap with `launchctl` /
`systemd --user`). Default data dir: `~/.local/share/consilium/`.

---

## 2. Install the CLI

The `consilium` entry point is already installed by the pip install above.
Configure it by pointing at your local API:

```bash
mkdir -p ~/.config/consilium
cat > ~/.config/consilium/client.yaml <<EOF
api_base: http://127.0.0.1:8421
token: <the same CONSILIUM_API_TOKEN from step 1>
EOF

# Sanity check
consilium --version
consilium templates list
```

### Typical CLI usage

```bash
# Simple debate (default template: product_concept)
consilium "Какой должна быть концепция коммерческой инфраструктуры?"

# Quick check with an existing pack
consilium -t quick_check --pack tanaa "Тема"

# With ad-hoc context files (uploaded as an ephemeral pack, cleaned up after)
consilium --context brief.md market.pdf "Тема"

# Just preview — cost estimate, no submission
consilium --preview "Тема"

# Skip confirmation prompt (good for scripts)
consilium --yes "Тема"

# Group into a project for archive filtering
consilium --project tanaa-property "Тема"

# Manage active debates
consilium jobs                    # list
consilium jobs status 42
consilium jobs cancel 42

# Archive
consilium archive search "концепция"
consilium archive get 42          # saves to ./consilium/0042.md
consilium archive stats --by model

# Budget
consilium budget usage
consilium budget daily            # markdown summary
consilium budget alerts           # 50/80/95% thresholds

# Packs
consilium packs create tanaa brief.md market.pdf
consilium packs show tanaa
consilium packs delete old
```

---

## 3. Install the MCP server in Claude Code

Edit `~/.claude.json` (Claude Code desktop config) and add a `mcpServers`
entry:

```json
{
  "mcpServers": {
    "consilium": {
      "command": "consilium-mcp",
      "env": {
        "CONSILIUM_API_BASE": "http://127.0.0.1:8421",
        "CONSILIUM_API_TOKEN": "<the same token>"
      }
    }
  }
}
```

Restart Claude Code. You should now see `consilium_*` tools available.

### Typical Claude Code usage

Open Claude Code in a project directory (e.g. `~/projects/tanaa/`) and
say something like:

> «Собери консилиум по концепции коммерческой инфраструктуры. Контекст:
> `brief.md` и `market.pdf`. Шаблон: `product_concept`.»

Claude Code will:

1. Call `consilium_preview` with `context_files=["brief.md", "market.pdf"]`
2. Show you the estimated cost and per-participant fit
3. After your confirmation, call `consilium_start` — you get a `job_id`
4. Call `consilium_wait` which streams progress (rounds completed,
   judge stage) and on completion downloads the markdown to
   `./consilium/{id}-{slug}.md` right inside the project
5. Report the TL;DR inline

Available tools:

| Tool | Purpose |
|------|---------|
| `consilium_preview` | Dry-run: cost + duration + per-participant fit, no side-effects |
| `consilium_start` | Submit a debate, returns `job_id` |
| `consilium_status` | Poll status of one debate |
| `consilium_wait` | Block until done, save markdown, return TL;DR (progress-reported) |
| `consilium_cancel` | Cancel in-flight debate |
| `consilium_archive_search` | FTS over archive |
| `consilium_archive_get` | Download markdown of archived debate |
| `consilium_archive_stats` | Aggregate by model/template/project |
| `consilium_archive_roi` | ROI rows |
| `consilium_packs_list` | List context packs |
| `consilium_pack_show` | Inspect one pack |
| `consilium_pack_create` | Create a pack from local files |
| `consilium_pack_delete` | Delete a pack |
| `consilium_templates_list` | Available YAML templates |
| `consilium_template_show` | Template details |
| `consilium_budget_usage` | Current spend |
| `consilium_budget_limits` | Configured limits |
| `consilium_budget_daily` | Markdown summary of today |
| `consilium_budget_alerts` | 50/80/95% thresholds fired |

---

## 4. Install the Telegram bot (optional — phone access)

See `consilium_server/bot/main.py` docstring for env vars. Requires:

- `TELEGRAM_BOT_TOKEN` from BotFather
- `TELEGRAM_ALLOWED_USER_IDS` (whitelist of Telegram user IDs)
- Same `CONSILIUM_API_BASE` + `CONSILIUM_API_TOKEN` as CLI/MCP

```bash
consilium-bot
```

Single-user, whitelist-enforced. Long-polling — no webhook needed.

---

## Troubleshooting

- **"Client config incomplete"** — set `CONSILIUM_API_BASE` +
  `CONSILIUM_API_TOKEN` env vars OR fill in `~/.config/consilium/client.yaml`.
- **"Не могу достучаться до API"** — is `consilium-api` running? Try
  `curl http://127.0.0.1:8421/templates -H "Authorization: Bearer $CONSILIUM_API_TOKEN"`.
- **Cost-guard 402** — expected if a template's estimate exceeds your
  configured `max_cost_per_job_usd`. Pass `--force` (CLI) / `force: true`
  (MCP) to bypass soft-caps. Hard-stop can't be bypassed.
- **MCP tool not showing in Claude Code** — verify `consilium-mcp` is on
  PATH (`which consilium-mcp`), and check Claude Code's MCP server logs.

---

## Architecture

See `docs/plans/2026-04-18-consilium-design.md` for the full design doc.

TL;DR: three clients → one HTTPS API → providers. API state is SQLite
(archive), filesystem (packs), env (limits). No Docker, no multi-tenancy,
single-user by design.

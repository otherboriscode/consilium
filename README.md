# Consilium

Multi-LLM council for developer product concept work. Run a debate
between Claude, GPT, Gemini, Grok, DeepSeek, and Perplexity on a concept
question; get a judge-synthesised markdown transcript with TL;DR,
consensus, open questions, and risks.

## Status

- ✅ Phase 1 — Foundation (providers, orchestrator)
- ✅ Phase 2 — Orchestrator hardening
- ✅ Phase 3 — YAML templates + context packs
- ✅ Phase 4 — SQLite archive with FTS search
- ✅ Phase 5 — Cost controls (5 levels of protection)
- ✅ Phase 6 — HTTPS API (FastAPI + SSE)
- ✅ Phase 7 — Telegram bot (aiogram, long-polling, whitelist)
- ✅ Phase 8 — MCP server + CLI
- ✅ Phase 9 — VPS deployment (nginx, Let's Encrypt, systemd)

Live at `https://consilium.89.167.73.98.nip.io` for Boris's private use.

## Three tiers of analysis

Not every question needs the full 6-model debate. Consilium offers a
cost-progressive ladder:

| Tier | Command | Cost | Time | When |
|------|---------|------|------|------|
| Solo | `consilium solo "вопрос"` | ~$0.07 | 20s | Sanity check, quick research |
| Devil's advocate | `consilium devil "вопрос"` | ~$0.18 | 60s | Decisions needing self-critique |
| Full council | `consilium "вопрос"` | ~$0.70 | 3min | Genuinely contested concept work |

See [docs/INSTALL.md §2](docs/INSTALL.md) for the decision rule.

## Three entry points, one engine

```
┌──────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Telegram bot    │     │  Claude Code │     │  consilium CLI  │
│  (phone access)  │     │     (MCP)    │     │  (scripts/cron) │
└────────┬─────────┘     └──────┬───────┘     └────────┬────────┘
         │                      │                      │
         └──────────────┬───────┴──────────────────────┘
                        ▼
                ┌───────────────┐
                │ consilium-api │  FastAPI + SSE, bearer auth
                └───────┬───────┘
                        ▼
              ┌─────────────────────┐
              │    orchestrator     │  rounds → judge → archive
              └──────────┬──────────┘
                         ▼
            ┌────────────────────────────┐
            │ Anthropic / OpenRouter /   │
            │ Perplexity (5+ models)     │
            └────────────────────────────┘
```

## Quick install

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[api,cli,mcp,bot,dev]"
```

Full setup — API server, CLI config, Claude Code MCP integration, Telegram
bot — is in **[docs/INSTALL.md](docs/INSTALL.md)**.

## Running tests

```bash
pytest                  # unit tests (fast, no network)
pytest -m integration   # real API smoke tests (requires provider keys)
```

Current: 487 tests across 7 layers.

## License

Private project, not published.

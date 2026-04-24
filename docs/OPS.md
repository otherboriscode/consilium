# Consilium — Operations Runbook

How to deploy, run, monitor, back up, and recover Consilium on Boris's VPS.

> **VPS:** `89.167.73.98` (Hetzner, Ubuntu 24.04.4 LTS, 8 GB RAM, 150 GB disk)
> **Domain:** `consilium.89.167.73.98.nip.io` (nip.io wildcard, no DNS to configure)
> **TLS:** Let's Encrypt cert, auto-renew via `certbot.timer`, expires 2026-07-23
> **Bot:** `@NeuroConcilium_bot` (Telegram), long-polling, whitelist-gated
> **Deploy status as of 2026-04-24:** ✅ API live, ✅ Bot running (whitelist
> pending), ⚠️ Backup deferred (no B2 creds yet), ⚠️ ufw + SSH hardening
> left untouched intentionally — see §7 Known issues.

---

## 1. Architecture

```
Mac (Boris)                            VPS 89.167.73.98
───────────                            ────────────────
Claude Code + MCP ──┐                 ┌─ systemd: consilium-api.service
CLI consilium ──────┼─ HTTPS 443 ─────┤   uvicorn 127.0.0.1:8421
Telegram (phone) ───┼─ via bot ───────┤
                    │                  └─ systemd: consilium-bot.service
                    ▼                     long-polling Telegram
              nginx :443
              ↑ Let's Encrypt cert (certbot.timer auto-renews)

Data:    /var/lib/consilium/{archive,packs,alerts_state.json,next_job_id.txt}
Config:  /etc/consilium/{.env,limits.yaml}      root:consilium 750
Code:    /opt/consilium/                        consilium:consilium
Logs:    journalctl -u consilium-{api,bot}
Backup:  restic → Backblaze B2, daily @ 03:00 UTC, retention 7d/4w/6m
```

---

## 2. Initial deployment (one-time)

### 2.1 VPS prep (as `root`)

```bash
ssh root@89.167.73.98

# 1. Sanity check OS + nginx + python
cat /etc/os-release | head -3
nginx -v
python3.12 --version    # if missing: apt install python3.12 python3.12-venv python3.12-dev

# 2. User + dirs
useradd -m -s /bin/bash consilium
mkdir -p /opt/consilium /etc/consilium /var/lib/consilium /var/log/consilium
chown -R consilium:consilium /opt/consilium /var/lib/consilium /var/log/consilium
chown root:consilium /etc/consilium
chmod 750 /etc/consilium
```

### 2.2 Clone code (as `consilium`)

```bash
sudo -u consilium -i
cd /opt/consilium
git clone https://github.com/otherboriscode/consilium.git .
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[api,bot]"
```

If the repo is private, generate an SSH deploy-key first:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ''
cat ~/.ssh/id_ed25519.pub
# → paste in github.com/otherboriscode/consilium → Settings → Deploy keys
```

### 2.3 Configs (as `root`)

```bash
# Copy templates from the repo and fill in real values
cp /opt/consilium/deploy/env.example          /etc/consilium/.env
cp /opt/consilium/deploy/limits.yaml.example  /etc/consilium/limits.yaml

vi /etc/consilium/.env       # fill in API keys, generate CONSILIUM_API_TOKEN
vi /etc/consilium/limits.yaml # adjust caps if needed

chown root:consilium /etc/consilium/.env /etc/consilium/limits.yaml
chmod 640 /etc/consilium/.env
chmod 644 /etc/consilium/limits.yaml
```

Generate a strong API token:
```bash
openssl rand -hex 32
# → put into /etc/consilium/.env as CONSILIUM_API_TOKEN
```

### 2.4 Run the bootstrap

```bash
bash /opt/consilium/deploy/install.sh
```

This:
- creates the `consilium` user (idempotent)
- installs systemd units from `deploy/systemd/`
- installs nginx site from `deploy/nginx/`
- installs the backup script + timer
- enables + restarts `consilium-api` and `consilium-bot`

Verify:
```bash
systemctl status consilium-api consilium-bot --no-pager | head -30
curl -s http://127.0.0.1:8421/templates -H "Authorization: Bearer $(grep ^CONSILIUM_API_TOKEN /etc/consilium/.env | cut -d= -f2)"
```

### 2.5 TLS via Let's Encrypt

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d consilium.89.167.73.98.nip.io \
    --non-interactive --agree-tos --email otherboris@gmail.com
systemctl reload nginx

# auto-renewal — should already exist
systemctl list-timers | grep certbot
```

Verify externally (from Mac):
```bash
curl -sI https://consilium.89.167.73.98.nip.io/ | head -3
# → HTTP/2 401  (no auth header) — proves TLS works
```

### 2.6 Firewall (if not already configured)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP (Let's Encrypt + redirect)
ufw allow 443/tcp    # HTTPS
ufw --force enable
ufw status verbose
```

Check SSH config (don't auto-edit — review and decide):
```bash
grep -E "^(PasswordAuthentication|PermitRootLogin|PubkeyAuthentication)" /etc/ssh/sshd_config
# Recommended:
#   PasswordAuthentication no
#   PermitRootLogin prohibit-password
#   PubkeyAuthentication yes
```

### 2.7 Backup (Backblaze B2 via restic)

Skip this section if B2 isn't set up yet — the backup timer will simply fail until it is. Configure later by completing the env vars and running `restic init`.

```bash
apt install -y restic

# B2 creds + restic password are in /etc/consilium/.env (see env.example)
set -a && source /etc/consilium/.env && set +a

# Initialize the repository (one-time, idempotent if it already exists)
restic init

# Test backup manually before relying on the timer
systemctl start consilium-backup
journalctl -u consilium-backup -n 50 --no-pager

# Verify a snapshot exists
restic snapshots
```

### 2.8 Provider-side hard limits (manual web actions — last line of defence)

These are the **last** line of defence. If our API-layer cost-guard fails (bug, leaked token), the provider stops your spend.

#### Anthropic
1. https://console.anthropic.com/settings/limits
2. Monthly spend limit → **$200**
3. Screenshot in 1Password

#### OpenRouter
1. https://openrouter.ai/settings/credits
2. Don't auto-refill; never top up above $200 at once

#### Perplexity
1. https://www.perplexity.ai/settings/api
2. Monthly usage cap → **$100**

#### Sanity check (monthly)
```bash
consilium budget usage
# Compare the "month_usd" total against each provider's reported usage:
#   - console.anthropic.com/settings/usage
#   - openrouter.ai/activity
#   - perplexity.ai/settings/api → Usage
```

---

## 3. Day-to-day operations

### Status & logs

```bash
systemctl status consilium-api consilium-bot
journalctl -u consilium-api -f          # tail
journalctl -u consilium-api --since=1h
journalctl -u consilium-bot --since=today

# All consilium units in one view
systemctl list-units 'consilium-*'
```

### Update code (every push from Mac)

```bash
ssh consilium@89.167.73.98 << 'EOF'
cd /opt/consilium
git pull
source .venv/bin/activate
pip install -e ".[api,bot]"
EOF

ssh root@89.167.73.98 "systemctl restart consilium-api consilium-bot"
```

~2 seconds of downtime. If you need to be sure nothing's mid-debate:
```bash
ssh consilium@89.167.73.98 "/opt/consilium/.venv/bin/consilium jobs --limit 50"
# Wait until status column shows no "running"
```

### Rotate the API token

```bash
NEW=$(openssl rand -hex 32)

# 1. On VPS
ssh root@89.167.73.98 "sed -i 's/^CONSILIUM_API_TOKEN=.*/CONSILIUM_API_TOKEN=$NEW/' /etc/consilium/.env && systemctl restart consilium-api consilium-bot"

# 2. On Mac
sed -i '' "s|^token:.*|token: $NEW|" ~/.config/consilium/client.yaml

# 3. In Claude Code config
#    Edit ~/.claude.json → mcpServers.consilium.env.CONSILIUM_API_TOKEN → $NEW
#    Restart Claude Code
```

Telegram bot token is separate (`TELEGRAM_BOT_TOKEN`) — only rotate that if it leaks.

### Change cost limits

```bash
ssh root@89.167.73.98
vi /etc/consilium/limits.yaml
systemctl restart consilium-api    # limits read at startup
```

### Restart everything (last resort)

```bash
ssh root@89.167.73.98 "systemctl restart consilium-api consilium-bot nginx"
```

---

## 4. Backups

### Check the latest snapshot
```bash
ssh root@89.167.73.98 "set -a && source /etc/consilium/.env && set +a && restic snapshots --latest 5"
```

### Manual backup
```bash
ssh root@89.167.73.98 "systemctl start consilium-backup && journalctl -u consilium-backup -n 30 --no-pager"
```

### Restore from backup
```bash
ssh root@89.167.73.98
set -a && source /etc/consilium/.env && set +a
restic snapshots                                  # find the snapshot ID
restic restore <snapshot-id> --target /tmp/restore
# Inspect /tmp/restore, then move what you need into place:
systemctl stop consilium-api consilium-bot
mv /var/lib/consilium /var/lib/consilium.broken
mv /tmp/restore/var/lib/consilium /var/lib/consilium
chown -R consilium:consilium /var/lib/consilium
systemctl start consilium-api consilium-bot
```

### Verify backup integrity
```bash
restic check                       # full check (slower)
restic check --read-data-subset=5% # 5% spot-check (what the daily timer does)
```

---

## 5. Troubleshooting

| Symptom | First check |
|---------|-------------|
| API returns 502 from nginx | `systemctl status consilium-api` — uvicorn down |
| Bot stopped responding | `systemctl status consilium-bot`, check Telegram token |
| TLS cert browser warning | `certbot certificates`, then `certbot renew` |
| Disk filling up | `du -sh /var/lib/consilium/*`, then `restic prune` |
| Cost-guard blocking everything | `consilium budget usage` vs `consilium budget limits` |
| `consilium-backup` failing | `journalctl -u consilium-backup`, verify B2 creds in `.env` |
| Mac CLI fails with "Network" | Confirm DNS: `nslookup consilium.89.167.73.98.nip.io` |
| `consilium-api` won't start | Check `EnvironmentFile=/etc/consilium/.env` exists with correct perms (640 root:consilium) |

### Useful one-liners

```bash
# Active jobs right now
consilium jobs

# Today's spend per model
consilium budget usage

# Last 5 archived debates
consilium archive list --limit 5

# Tail SSE events in real time (if a job is running)
ssh consilium@89.167.73.98 "journalctl -u consilium-api -f | grep -i 'event\|job'"
```

---

## 6. Disaster recovery

If the VPS is gone entirely:

1. Provision a fresh Debian 12 / Ubuntu 22.04 VPS at the same IP (or update DNS).
2. Run sections 2.1 → 2.4 of this doc.
3. Restore from the latest restic snapshot (section 4 → Restore).
4. Run sections 2.5 → 2.6 (TLS + firewall).
5. The Telegram bot will pick up automatically — no Telegram-side changes needed.
6. Mac CLI/MCP keep working as long as DNS resolves (nip.io is automatic) and the API token is unchanged (it's restored in `/etc/consilium/.env`).

Estimated time to full recovery: **~1 hour** (mostly waiting on `pip install` and `certbot`).

---

## 7. Known issues / TODO (as of 2026-04-24)

### Open items

- [x] ~~`TELEGRAM_ALLOWED_USER_IDS` is empty~~ — **filled in 2026-04-24,
  user_id = `74859890`. Bot is active.**
  To change/add:
  ```bash
  ssh root@89.167.73.98 "sed -i 's/^TELEGRAM_ALLOWED_USER_IDS=.*/TELEGRAM_ALLOWED_USER_IDS=<CSV_OF_IDS>/' /etc/consilium/.env && systemctl restart consilium-bot"
  # Get user_id by messaging @userinfobot on Telegram.
  ```

- [ ] **Backblaze B2 credentials not configured** —
  `consilium-backup.service`/`timer` are **not** installed yet.
  When you have a B2 bucket, add `B2_ACCOUNT_ID`, `B2_APPLICATION_KEY`,
  `RESTIC_REPOSITORY`, `RESTIC_PASSWORD` to `/etc/consilium/.env`, then:
  ```bash
  ssh root@89.167.73.98 "apt install -y restic && \
      install -m 644 /opt/consilium/deploy/systemd/consilium-backup.service /etc/systemd/system/ && \
      install -m 644 /opt/consilium/deploy/systemd/consilium-backup.timer /etc/systemd/system/ && \
      install -m 750 -o root -g consilium /opt/consilium/deploy/backup/consilium-backup.sh /usr/local/bin/ && \
      systemctl daemon-reload && \
      set -a && source /etc/consilium/.env && set +a && restic init && \
      systemctl enable --now consilium-backup.timer"
  ```

- [ ] **Provider-side hard limits** (manual web actions — see §2.8):
  Anthropic $200/mo, OpenRouter no-refill cap, Perplexity $100/mo.
  Keep screenshots in 1Password.

### Security hardening — deferred, safe to ignore for single-user MVP

- [ ] **ufw firewall is `inactive`** on the VPS. Ports 22/80/443 are open via
  the cloud-provider-level firewall (or not — we haven't audited), which is
  fine for a single-tenant box. To enable ufw (carefully, to avoid locking
  out SSH):
  ```bash
  ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
  ```
- [ ] **SSH: `PasswordAuthentication yes` and `PermitRootLogin yes`** in
  `/etc/ssh/sshd_config`. Recommend switching to `prohibit-password` +
  `PasswordAuthentication no` once you confirm your key-based login works
  from all devices you use.

### Nice-to-have, not urgent

- [ ] `pip-audit` monthly: `pip-audit -r <(/opt/consilium/.venv/bin/pip freeze)`.
- [ ] CLI `consilium -t <tpl> "тема"` shortcut is broken — first arg is
  treated as `<command>` not as positional. Works fine with explicit
  `consilium debate -t <tpl> "тема"`. Minor UX fix for later.
- [ ] Perplexity `sonar-deep-research` leaks `<think>...</think>` tags
  into debate output (visible in debate #2 transcript). Consider a
  post-process filter in the orchestrator.

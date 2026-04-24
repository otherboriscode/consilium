#!/bin/bash
# Idempotent VPS bootstrap for Consilium. Run as root on the target VPS
# AFTER you've cloned the repo to /opt/consilium and filled in
# /etc/consilium/.env (see docs/OPS.md for the full variable list).
#
# Usage:
#   ssh root@VPS "bash -s" < deploy/install.sh
# OR (after rsync of the repo):
#   bash /opt/consilium/deploy/install.sh
#
# What it does:
#   1. Creates /opt /var/lib /etc/consilium dirs and the consilium user
#   2. Installs systemd units from deploy/systemd/
#   3. Installs nginx site from deploy/nginx/
#   4. Installs backup script + timer
#   5. Reloads systemd, enables + starts services
#
# What it does NOT do (you do these manually, see docs/OPS.md):
#   - Get TLS cert from Let's Encrypt (`certbot --nginx -d ...`)
#   - Initialize the restic repository (`restic init`)
#   - Configure ufw firewall
#   - Set provider-side hard limits

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/consilium}"
NGINX_DOMAIN="${NGINX_DOMAIN:-consilium.89.167.73.98.nip.io}"

if [[ $EUID -ne 0 ]]; then
    echo "Run as root (use sudo)." >&2
    exit 1
fi

if [[ ! -d "$REPO_ROOT" ]]; then
    echo "Repo not at $REPO_ROOT. Clone it first:"
    echo "  cd /opt && git clone https://github.com/otherboriscode/consilium.git"
    exit 1
fi

echo "==> 1/5 Creating user + directories"
id -u consilium &>/dev/null || useradd -m -s /bin/bash consilium

mkdir -p /etc/consilium /var/lib/consilium /var/log/consilium
chown -R consilium:consilium /var/lib/consilium /var/log/consilium "$REPO_ROOT"
chown -R root:consilium /etc/consilium
chmod 750 /etc/consilium

if [[ ! -f /etc/consilium/.env ]]; then
    echo "WARNING: /etc/consilium/.env doesn't exist."
    echo "  Create it (see docs/OPS.md for variable list) and re-run."
    exit 1
fi
chmod 640 /etc/consilium/.env
chown root:consilium /etc/consilium/.env

if [[ -f /etc/consilium/limits.yaml ]]; then
    chmod 644 /etc/consilium/limits.yaml
fi

echo "==> 2/5 Installing systemd units"
install -m 644 "$REPO_ROOT/deploy/systemd/consilium-api.service" \
    /etc/systemd/system/consilium-api.service
install -m 644 "$REPO_ROOT/deploy/systemd/consilium-bot.service" \
    /etc/systemd/system/consilium-bot.service
install -m 644 "$REPO_ROOT/deploy/systemd/consilium-backup.service" \
    /etc/systemd/system/consilium-backup.service
install -m 644 "$REPO_ROOT/deploy/systemd/consilium-backup.timer" \
    /etc/systemd/system/consilium-backup.timer

echo "==> 3/5 Installing nginx site"
install -m 644 "$REPO_ROOT/deploy/nginx/consilium.conf" \
    /etc/nginx/sites-available/consilium
ln -sf /etc/nginx/sites-available/consilium /etc/nginx/sites-enabled/consilium
nginx -t

echo "==> 4/5 Installing backup script"
install -m 750 -o root -g consilium "$REPO_ROOT/deploy/backup/consilium-backup.sh" \
    /usr/local/bin/consilium-backup.sh

echo "==> 5/5 Reloading systemd + enabling services"
systemctl daemon-reload
systemctl enable consilium-api consilium-bot
# Backup timer enabled only if B2 creds look filled in.
if grep -q '^B2_ACCOUNT_ID=..' /etc/consilium/.env 2>/dev/null; then
    systemctl enable consilium-backup.timer
else
    echo "  (skipping consilium-backup.timer — B2 creds missing; add them to .env later)"
fi
systemctl reload nginx

# Start API + bot only if a venv exists at the expected path.
if [[ -x "$REPO_ROOT/.venv/bin/consilium-api" ]]; then
    systemctl restart consilium-api consilium-bot
    sleep 2
    systemctl --no-pager status consilium-api consilium-bot | head -25
else
    echo "NOTE: $REPO_ROOT/.venv not found — skipping start. Build the venv first:"
    echo "  sudo -u consilium bash -lc 'cd $REPO_ROOT && python3.12 -m venv .venv && source .venv/bin/activate && pip install -e \".[api,bot]\"'"
fi

echo
echo "==> Done. Next manual steps (see docs/OPS.md):"
echo "  1. certbot --nginx -d $NGINX_DOMAIN  (TLS cert)"
echo "  2. Set TELEGRAM_ALLOWED_USER_IDS in /etc/consilium/.env (your Telegram user_id)"
echo "  3. Set B2 creds + restic init (optional, for backups)"
echo "  4. ufw allow 22/tcp 80/tcp 443/tcp && ufw enable"
echo "  5. Set provider-side hard limits in web consoles (Anthropic, OpenRouter, Perplexity)"

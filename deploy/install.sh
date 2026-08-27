#!/bin/bash
# Run on a fresh Hetzner Ubuntu 24.04 CX23 as root.
# Usage: sudo bash /opt/eshop/deploy/install.sh
set -euo pipefail

APP_DIR=/opt/eshop
DATA_DIR=/var/lib/eshop
REPO_URL="${REPO_URL:-https://github.com/panagiod/print-me-maybe.git}"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip git sqlite3 \
  debian-keyring debian-archive-keyring apt-transport-https curl gnupg

if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

id -u eshop >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin eshop
mkdir -p "$APP_DIR" "$DATA_DIR" "$DATA_DIR/backups"

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

git config --system --add safe.directory "$APP_DIR"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f /etc/eshop.env ]; then
  cp "$APP_DIR/deploy/env.example" /etc/eshop.env
  SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
  ADMIN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  sed -i "s|^SESSION_SECRET=.*|SESSION_SECRET=${SECRET}|" /etc/eshop.env
  sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN}|" /etc/eshop.env
  echo "Generated ADMIN_PASSWORD (also stored in /etc/eshop.env): ${ADMIN}"
  echo "Edit /etc/eshop.env (SHOP_URL, STRIPE_SECRET_KEY, RESEND_*) then: systemctl restart eshop"
fi

cp "$APP_DIR/deploy/eshop.service" /etc/systemd/system/eshop.service
if [ ! -f /etc/caddy/Caddyfile.eshop.bak ]; then
  cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.eshop.bak 2>/dev/null || true
fi
cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
chmod 750 "$APP_DIR/deploy/backup.sh" "$APP_DIR/deploy/deploy.sh" || true

chown -R eshop:eshop "$APP_DIR" "$DATA_DIR"
chown root:eshop /etc/eshop.env
chmod 640 /etc/eshop.env

systemctl daemon-reload
systemctl enable --now eshop
systemctl enable --now caddy
systemctl reload caddy || systemctl restart caddy
systemctl --no-pager --full status eshop || true
echo "Health: curl -s http://127.0.0.1:8000/health"
echo "Put your domain in /etc/caddy/Caddyfile, then: systemctl reload caddy"

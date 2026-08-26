#!/bin/bash
# Pull latest main from GitHub and restart services. Run on the Hetzner server.
# Bootstrap once with install.sh before using this script or GitHub Actions deploy.
set -euo pipefail

APP_DIR=/opt/eshop

if [ ! -d "$APP_DIR/.git" ]; then
  echo "Missing $APP_DIR — run: bash /opt/eshop/deploy/install.sh" >&2
  exit 1
fi

cd "$APP_DIR"
git fetch origin main
git reset --hard origin/main

"$APP_DIR/.venv/bin/pip" install -q -r requirements.txt

cp "$APP_DIR/deploy/eshop.service" /etc/systemd/system/eshop.service
cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
chmod 750 "$APP_DIR/deploy/backup.sh" || true

chown -R eshop:eshop "$APP_DIR" /var/lib/eshop

systemctl daemon-reload
systemctl restart eshop
systemctl reload caddy 2>/dev/null || systemctl restart caddy

curl -sf http://127.0.0.1:8000/health
echo
echo "Deploy OK ($(git rev-parse --short HEAD))"

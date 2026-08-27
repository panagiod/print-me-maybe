#!/bin/bash
# Pull latest main from GitHub and restart services. Run on the Hetzner server.
# Bootstrap once with install.sh before using this script or GitHub Actions deploy.
set -euo pipefail

APP_DIR=/opt/eshop

if [ ! -d "$APP_DIR/.git" ]; then
  echo "Missing $APP_DIR — run: bash /opt/eshop/deploy/install.sh" >&2
  exit 1
fi

git config --system --add safe.directory "$APP_DIR" 2>/dev/null || true

cd "$APP_DIR"
sudo -u eshop git -C "$APP_DIR" fetch origin main
sudo -u eshop git -C "$APP_DIR" reset --hard origin/main

if [ ! -x "$APP_DIR/.venv/bin/uvicorn" ]; then
  echo "No venv yet — running install.sh"
  bash "$APP_DIR/deploy/install.sh"
fi

sudo -u eshop "$APP_DIR/.venv/bin/pip" install -q -r requirements.txt

cp "$APP_DIR/deploy/eshop.service" /etc/systemd/system/eshop.service
cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
chmod 750 "$APP_DIR/deploy/backup.sh" "$APP_DIR/deploy/deploy.sh" || true

if ! crontab -l 2>/dev/null | grep -qF "/opt/eshop/deploy/backup.sh"; then
  line="15 3 * * * /opt/eshop/deploy/backup.sh >> /var/lib/eshop/backups/cron.log 2>&1"
  current="$(crontab -l 2>/dev/null || true)"
  printf '%s\n%s\n' "$current" "$line" | crontab -
  echo "Installed nightly SQLite backup cron (03:15 UTC)"
fi

chown -R eshop:eshop "$APP_DIR" /var/lib/eshop

systemctl daemon-reload
systemctl restart eshop
systemctl reload caddy 2>/dev/null || systemctl restart caddy 2>/dev/null || echo "WARN: caddy not running (OK before DNS/HTTPS)" >&2

if ! systemctl is-active --quiet eshop; then
  echo "eshop service is not active:" >&2
  systemctl --no-pager status eshop || true
  journalctl -u eshop -n 40 --no-pager || true
  exit 1
fi

for _ in 1 2 3 4 5; do
  if curl -sf http://127.0.0.1:8000/health; then
    echo
    echo "Deploy OK ($(sudo -u eshop git -C "$APP_DIR" rev-parse --short HEAD))"
    exit 0
  fi
  sleep 2
done

echo "Health check failed — eshop service logs:" >&2
systemctl --no-pager status eshop || true
journalctl -u eshop -n 40 --no-pager || true
exit 1

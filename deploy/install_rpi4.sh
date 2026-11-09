#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
if [[ "$EUID" -eq 0 ]]; then echo 'Run as normal user (pi), not root.' >&2; exit 1; fi
if [[ ! -f "$ROOT/app/launcher.py" ]]; then echo 'Missing app/launcher.py' >&2; exit 1; fi
if [[ ! -f "$ROOT/.env" ]]; then echo 'Missing .env: transfer it securely from Windows first.' >&2; exit 1; fi
if [[ ! -f "$ROOT/data/giveaways.sqlite3" ]]; then echo 'Missing database: transfer a consistent SQLite backup first.' >&2; exit 1; fi
if [[ ! -d "$ROOT/.venv" ]]; then python3 -m venv "$ROOT/.venv"; fi
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
"$ROOT/.venv/bin/python" "$ROOT/scripts/db_maintenance.py" check
# Do not print secrets from .env.
chmod 600 "$ROOT/.env"
chmod 700 "$ROOT/data"
SERVICE_FILE="/etc/systemd/system/ayla-giveaway.service"
TEMP_FILE="$(mktemp)"
trap 'rm -f "$TEMP_FILE"' EXIT
cat > "$TEMP_FILE" <<EOF
[Unit]
Description=Ayla Giveaway Hunter v3.0
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python $ROOT/app/launcher.py
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=20
TimeoutStopSec=40
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 "$TEMP_FILE" "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable ayla-giveaway.service
sudo systemctl restart ayla-giveaway.service
sudo systemctl --no-pager status ayla-giveaway.service || true
printf '\nLogs: sudo journalctl -u ayla-giveaway -n 80 --no-pager\n'

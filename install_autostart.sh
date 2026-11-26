#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install_autostart.sh — Auto-start The Frame V2 on Pi boot
#  Run once on your Raspberry Pi inside The_Frame_V2:
#    ./install_autostart.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${USER:-$(whoami)}"
VENV_PYTHON="${VENV_PYTHON:-$HOME/.virtualenvs/pimoroni/bin/python}"
SERVICE_NAME="the-frame"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Error: Pimoroni virtualenv Python not found at $VENV_PYTHON"
    echo "Set VENV_PYTHON=/path/to/python and re-run."
    exit 1
fi

echo "Installing systemd service: $SERVICE_FILE"
echo "  User:   $RUN_USER"
echo "  Dir:    $APP_DIR"
echo "  Python: $VENV_PYTHON"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=The Frame V2 — E-Ink Weather & Photo Frame
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_PYTHON} ${APP_DIR}/main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo ""
echo "Done! ${SERVICE_NAME} is running and will auto-start on every reboot."
echo ""
echo "Useful commands:"
echo "  Check status:   sudo systemctl status ${SERVICE_NAME}"
echo "  View live logs: journalctl -u ${SERVICE_NAME} -f"
echo "  Restart (after git pull): sudo systemctl restart ${SERVICE_NAME}"
echo "  Stop:           sudo systemctl stop ${SERVICE_NAME}"

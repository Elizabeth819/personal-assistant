#!/usr/bin/env bash
# Start the personal-assistant API for the iPhone PWA.
# - Binds 0.0.0.0:${PA_PORT:-8780} so the phone on LAN/USB can reach it.
# - Logs LAN URL + writes PID to .pa.pid for stop.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PA_PORT:-8780}"
HOST="${PA_HOST:-0.0.0.0}"

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"

echo "==> Starting PA on http://${LAN_IP}:${PORT}"
echo "    iPhone Safari → http://${LAN_IP}:${PORT}/  (Add to Home Screen)"
echo "    or            → http://pa-agent.local:${PORT}/"
echo

exec uv run uvicorn pa.api.app:app --host "$HOST" --port "$PORT" --log-level info

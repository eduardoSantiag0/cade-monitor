#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p logs data

read_env_value() {
  key="$1"
  if [ ! -f .env ]; then
    return 1
  fi
  line=$(grep -E "^${key}=" .env | tail -n 1 || true)
  if [ -z "$line" ]; then
    return 1
  fi
  value=${line#*=}
  value=${value%\"}
  value=${value#\"}
  value=${value%\'}
  value=${value#\'}
  printf '%s' "$value"
}

PORT=$(read_env_value WHATSAPP_WEBBOT_PORT || printf '18188')
TOKEN=$(read_env_value WHATSAPP_WEBBOT_TOKEN || true)
AUTH_DIR=$(read_env_value WHATSAPP_WEBBOT_AUTH_DIR || true)

if [ ! -d wa-bot/node_modules ]; then
  echo "Dependencias do WhatsApp bot nao instaladas. Rode: sh scripts/install_whatsapp_bot.sh" >&2
  exit 1
fi

if ! pgrep -u "$USER" -f "node .*wa-bot/server.js" >/dev/null 2>&1; then
  WHATSAPP_WEBBOT_PORT="$PORT" \
  WHATSAPP_WEBBOT_TOKEN="$TOKEN" \
  WHATSAPP_WEBBOT_AUTH_DIR="$AUTH_DIR" \
  nohup node wa-bot/server.js >> logs/whatsapp.log 2>&1 &
fi

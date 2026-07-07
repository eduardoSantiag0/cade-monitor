#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js nao encontrado no servidor." >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm nao encontrado no servidor." >&2
  exit 1
fi

cd wa-bot
npm install --omit=dev
node -v
npm -v

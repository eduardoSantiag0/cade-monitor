#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p logs data

choose_python() {
  for candidate in .venv/bin/python python3.13 python3.12 python3 python; do
    if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  echo "Python 3.10+ nao encontrado. Rode: sh scripts/rebuild_venv.sh" >&2
  return 1
}

PY=$(choose_python)
PORT=${PORT:-8000}
HOST=${HOST:-127.0.0.1}
PATTERN="cademon serve .*--port $PORT"

if ! pgrep -u "$USER" -f "$PATTERN" >/dev/null 2>&1; then
  nohup "$PY" -m cademon serve --host "$HOST" --port "$PORT" >> logs/web.log 2>&1 &
fi

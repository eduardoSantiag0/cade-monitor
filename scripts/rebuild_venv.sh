#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."

choose_base_python() {
  for candidate in python3.13 python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  echo "Python 3.10+ nao encontrado no servidor." >&2
  return 1
}

PY=$(choose_base_python)
STAMP=$(date +%Y%m%d-%H%M%S)

if [ -d .venv ]; then
  mv .venv ".venv.old-$STAMP"
fi

"$PY" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip >/dev/null 2>&1 || true
if [ -s requirements.txt ]; then
  python -m pip install -r requirements.txt
fi
python -m cademon init
python -V

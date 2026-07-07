
from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | os.PathLike[str] = '.env') -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def format_env_value(value: str) -> str:
    clean = str(value or '').replace('\r', '').replace('\n', ' ').strip()
    if not clean:
        return ''
    if any(ch.isspace() for ch in clean) or clean.startswith(('"', "'")) or '#' in clean:
        return '"' + clean.replace('"', '\"') + '"'
    return clean


def update_env_file(path: str | os.PathLike[str], updates: dict[str, str]) -> None:
    env_path = Path(path)
    lines = env_path.read_text(encoding='utf-8').splitlines() if env_path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            output.append(raw_line)
            continue
        key = stripped.split('=', 1)[0].strip()
        if key in updates:
            output.append(f'{key}={format_env_value(updates[key])}')
            seen.add(key)
        else:
            output.append(raw_line)

    missing = [key for key in updates if key not in seen]
    if missing:
        if output and output[-1].strip():
            output.append('')
        output.append('# Atualizado pelo painel web do Meskade')
        for key in missing:
            output.append(f'{key}={format_env_value(updates[key])}')

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text('\n'.join(output).rstrip() + '\n', encoding='utf-8')

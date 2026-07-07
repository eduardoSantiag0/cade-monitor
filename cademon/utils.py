
from __future__ import annotations

from datetime import datetime, timezone
from html import escape as html_escape
from urllib.parse import urlparse


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    cleaned = value.replace(';', ',').replace('\n', ',')
    return [part.strip() for part in cleaned.split(',') if part.strip()]


def as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == '':
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'sim', 'on'}


def as_int(value: str | None, default: int) -> int:
    try:
        if value is None or value == '':
            return default
        return int(value)
    except ValueError:
        return default


def looks_like_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def validate_public_url(value: str) -> str:
    source = value.strip()
    if not source:
        raise ValueError('Informe uma URL publica ou o numero do processo/protocolo.')
    parsed = urlparse(source)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('A URL precisa iniciar com http:// ou https://.')
        return source
    if len(source) < 4:
        raise ValueError('Informe um numero de processo/protocolo valido.')
    return source


def h(value: object) -> str:
    return html_escape('' if value is None else str(value), quote=True)

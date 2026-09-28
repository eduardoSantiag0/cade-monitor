"""
Geração de convite de calendário (.ics) por template de texto puro — sem
dependência nova (Princípio VIII; ver research.md). RFC 5545 mínimo: evento de
dia inteiro, `METHOD:REQUEST`/`METHOD:CANCEL`, dobra de linha em 75 octetos.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

_PRODID = '-//cade-monitor//agenda//PT-BR'


def _fold_line(line: str) -> str:
    """RFC 5545 §3.1: linha maior que 75 octetos é dobrada com CRLF + espaço."""
    data = line.encode('utf-8')
    if len(data) <= 75:
        return line
    parts = []
    start = 0
    limit = 75
    while start < len(data):
        end = min(start + limit, len(data))
        # Nunca corta um caractere UTF-8 multibyte ao meio.
        while end < len(data) and (data[end] & 0xC0) == 0x80:
            end -= 1
        parts.append(data[start:end].decode('utf-8'))
        start = end
        limit = 74  # a partir da 2ª linha, 1 octeto vira o espaço de continuação
    return '\r\n '.join(parts)


def _dtstamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def build_ics(uid: str, sequence: int, method: str, summary: str, event_date: date) -> bytes:
    """`method` ∈ 'REQUEST', 'CANCEL'. Evento de dia inteiro (`VALUE=DATE`)."""
    status = 'CANCELLED' if method == 'CANCEL' else 'CONFIRMED'
    dtstart = event_date.strftime('%Y%m%d')
    dtend = (event_date.toordinal() + 1)
    dtend_str = date.fromordinal(dtend).strftime('%Y%m%d')
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        f'PRODID:{_PRODID}',
        f'METHOD:{method}',
        'CALSCALE:GREGORIAN',
        'BEGIN:VEVENT',
        f'UID:{uid}',
        f'DTSTAMP:{_dtstamp()}',
        f'DTSTART;VALUE=DATE:{dtstart}',
        f'DTEND;VALUE=DATE:{dtend_str}',
        f'SUMMARY:{summary}',
        f'SEQUENCE:{sequence}',
        f'STATUS:{status}',
        'TRANSP:TRANSPARENT',
        'X-MICROSOFT-CDO-ALLDAYEVENT:TRUE',
        'END:VEVENT',
        'END:VCALENDAR',
    ]
    body = '\r\n'.join(_fold_line(line) for line in lines) + '\r\n'
    return body.encode('utf-8')

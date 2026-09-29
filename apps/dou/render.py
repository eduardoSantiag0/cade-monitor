"""
Formatação do digest DOU (spec 009) para e-mail: negrito de título/partes, truncamento
de despacho longo, destaque (fundo amarelo) por termo monitorado, rodapé de atas/pautas.

Os regexes de extração de padrões (título de caso, rótulo de partes) foram calibrados
contra boletins reais do CADE. Versão simplificada para o v1: sem a extração
completa de despacho (cabeçalho SEI, assinatura eletrônica etc. — ver research.md).
"""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from datetime import datetime

WEEKDAYS_PT = [
    'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira',
    'sexta-feira', 'sábado', 'domingo',
]

_CASE_TITLE_RE = re.compile(
    r'(?:Ato de Concentração'
    r'|Inquérito(?:\s+Ad?ministrativo)?'
    r'|Processo(?:\s+Ad?ministrativo)?(?:\s+de\s+Ato de Concentração)?'
    r'|Procedimento(?:\s+(?:Ad?ministrativo|Preparatório))?'
    r'|Averiguação\s+Preliminar'
    r'|Recurso(?:\s+(?:Volunt[áa]rio|de\s+Of[íi]cio|Ad?ministrativo))?'
    r'|Representação)'
    r'\s+n[º°ᵒo]?\s*[\d./-]*\d',
    re.I,
)
_PARTY_LABEL = r'(?:Requerentes?|Partes|Part[ií]cipes|Representante|Representad[oa]s?|Recorrentes?|Recorrid[oa]s?)'
_NEXT_LABEL = (
    r'(?:Advogad[oa]s?|Natureza|Setor|Representad[oa]s?|Representante|Recorrentes?|Recorrid[oa]s?'
    r'|Relator|Recurso|Terceir[oa]s?|Interessad[oa]s?|DESPACHO|ESP[ÉE]CIE|OBJETO|Processo\s+n)'
)
_PARTY_RE = re.compile(rf'({_PARTY_LABEL}\s*:\s*)(.+?)(?=\s{_NEXT_LABEL}\b|$)', re.S | re.I)

DESPACHO_HEAD_CHARS = 900
DESPACHO_TAIL_CHARS = 700

HIGHLIGHT_STYLE = 'background-color:#fff200;color:inherit'
_HIGHLIGHT_SPACER = (
    '<div style="height:12px;line-height:12px;font-size:12px;mso-line-height-rule:exactly">&nbsp;</div>'
)

_SIGNATURE_TEXT = 'Abs.,'
_EMAIL_STYLE = (
    'font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.55;'
    'color:#1a1a1a;max-width:760px'
)


def fold(text: object) -> str:
    normalized = unicodedata.normalize('NFKD', str(text or '').lower())
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def greeting(now: datetime) -> str:
    hour = now.hour
    if hour < 12:
        return 'bom dia'
    if hour < 18:
        return 'boa tarde'
    return 'boa noite'


def format_date_pt(day) -> str:
    weekday = WEEKDAYS_PT[day.weekday()]
    return f'{weekday}, {day.day}.{day.month}.{day.year}'


def truncate_despacho(text: str, head: int = DESPACHO_HEAD_CHARS, tail: int = DESPACHO_TAIL_CHARS) -> str:
    """Despacho longo: mantém o início + a conclusão, com '(...)' no meio, cortando em
    fronteira de frase para não cortar palavra no meio."""
    clean = re.sub(r'\s+', ' ', text or '').strip()
    if len(clean) <= head + tail + 80:
        return clean
    head_cut = clean[:head]
    dot = max(head_cut.rfind('. '), head_cut.rfind('; '))
    if dot > head * 0.5:
        head_cut = head_cut[:dot + 1]
    tail_cut = clean[-tail:]
    dot = tail_cut.find('. ')
    if 0 <= dot < tail * 0.5:
        tail_cut = tail_cut[dot + 2:]
    return f'{head_cut.strip()} (...) {tail_cut.strip()}'


def _bold_html(escaped: str) -> str:
    escaped = _CASE_TITLE_RE.sub(lambda m: f'<strong>{m.group(0)}</strong>', escaped)
    escaped = _PARTY_RE.sub(lambda m: f'{m.group(1)}<strong>{m.group(2).strip()}</strong>', escaped)
    return escaped


def _term_regex(term: str) -> re.Pattern | None:
    needle = fold(term).strip()
    if not needle:
        return None
    parts = [re.escape(piece) for piece in needle.split()]
    return re.compile(r'(?<!\w)' + r'\s+'.join(parts) + r'(?!\w)')


def _is_highlighted(block_text: str, terms: list[str]) -> bool:
    folded = fold(block_text)
    for term in terms:
        pattern = _term_regex(term)
        if pattern and pattern.search(folded):
            return True
    return False


def _block_html(block_text: str, terms: list[str]) -> str:
    highlighted = _is_highlighted(block_text, terms)
    inner = _bold_html(html_lib.escape(block_text))
    if not highlighted:
        return f'<p style="margin:0 0 12px">{inner}</p>'
    return f'<p style="margin:0;{HIGHLIGHT_STYLE}">{inner}</p>{_HIGHLIGHT_SPACER}'


def _wrap_email_html(body: list[str]) -> str:
    return (f'<html><body style="{_EMAIL_STYLE}"><div style="{_EMAIL_STYLE}">'
            + ''.join(body) + '</div></body></html>')


def _ata_line_text(item: dict) -> str:
    label = (item.get('titulo') or '').strip()
    url = (item.get('url') or '').strip()
    if not label:
        return ''
    return f'{label}: {url}' if url else label


def _ata_line_html(item: dict) -> str:
    label = (item.get('titulo') or '').strip()
    url = (item.get('url') or '').strip()
    if not label:
        return ''
    titulo = f'<strong style="text-decoration:underline">{html_lib.escape(label)}</strong>'
    if url:
        safe_url = html_lib.escape(url)
        return f'<p style="margin:0 0 8px">{titulo}: <a href="{safe_url}">{safe_url}</a></p>'
    return f'<p style="margin:0 0 8px">{titulo}</p>'


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def build_blocks(dou_data: dict) -> tuple[list[str], list[str]]:
    editais = [_clean(item.get('text', '')) or item.get('titulo', '') for item in dou_data.get('editais', [])]
    despachos = [truncate_despacho(item.get('text', '')) for item in dou_data.get('despachos', [])]
    return editais, despachos


def digest_subject(reference_date) -> str:
    return f'DOU CADE | {reference_date.day}.{reference_date.month}.{reference_date.year}'


def render_digest_text(dou_data: dict, terms: list[str], reference_date, now: datetime) -> str:
    editais, despachos = build_blocks(dou_data)
    atas = [line for line in (_ata_line_text(a) for a in dou_data.get('atas', [])) if line]
    parts = [f'Prezados, {greeting(now)}!']
    if not editais and not despachos and not atas:
        parts.append(f'Não houve publicações do CADE no DOU de {format_date_pt(reference_date)}.')
    else:
        parts.append(f'Encaminho abaixo as publicações do DOU de {format_date_pt(reference_date)}.')
        if editais:
            parts.append('Edital:' if len(editais) == 1 else 'Editais:')
            parts.extend(editais)
        if despachos:
            parts.append('Despacho:' if len(despachos) == 1 else 'Despachos:')
            parts.extend(despachos)
        parts.extend(atas)
    parts.append(_SIGNATURE_TEXT)
    return '\n\n'.join(parts)


def render_digest_html(dou_data: dict, terms: list[str], reference_date, now: datetime) -> str:
    editais, despachos = build_blocks(dou_data)
    atas = [line for line in (_ata_line_html(a) for a in dou_data.get('atas', [])) if line]
    body: list[str] = [f'<p style="margin:0 0 12px">Prezados, {greeting(now)}!</p>']
    if not editais and not despachos and not atas:
        body.append(
            f'<p style="margin:0 0 16px">Não houve publicações do CADE no DOU de '
            f'{html_lib.escape(format_date_pt(reference_date))}.</p>'
        )
    else:
        body.append(
            f'<p style="margin:0 0 16px">Encaminho abaixo as publicações do DOU de '
            f'{html_lib.escape(format_date_pt(reference_date))}.</p>'
        )
        if editais:
            body.append('<p style="margin:0 0 8px"><strong style="text-decoration:underline">Editais:</strong></p>')
            body.extend(_block_html(text, terms) for text in editais)
        if despachos:
            body.append('<p style="margin:16px 0 8px"><strong style="text-decoration:underline">Despachos:</strong></p>')
            body.extend(_block_html(text, terms) for text in despachos)
        if atas:
            body.append('<p style="margin:16px 0 8px"></p>')
            body.extend(atas)
    body.append(f'<p style="margin:4px 0 0">{_SIGNATURE_TEXT}</p>')
    return _wrap_email_html(body)


# ===================== Antecipação da véspera / confirmação (User Stories 2 e 3) =====

def pubdou_subject(reference_date) -> str:
    return f'Publicação DOU | {reference_date.day}.{reference_date.month}.{reference_date.year}'


def item_lead_reference(item: dict) -> str:
    """Rótulo humano do item para a lista de 'exceto ...' — o título de caso já
    capturado na extração (parsers.py), ou os 60 primeiros caracteres do texto."""
    return (item.get('titulo') or '').strip() or (item.get('text') or '')[:60].strip()


def _items_block_text(items: list[dict]) -> list[str]:
    return [truncate_despacho(item.get('text', '')) for item in items]


def _items_block_html(items: list[dict], terms: list[str]) -> list[str]:
    return [_block_html(truncate_despacho(item.get('text', '')), terms) for item in items]


def render_pubdou_text(items: list[dict], reference_date, now: datetime) -> str:
    """Antecipação/complemento da véspera (texto) — mesmo formato do digest, sem os
    cabeçalhos de seção (a antecipação não distingue edital/despacho)."""
    parts = [f'Prezados, {greeting(now)}!']
    if not items:
        parts.append(f'Não tivemos publicações previstas para o DOU de {format_date_pt(reference_date)}.')
    else:
        parts.append(f'Encaminho abaixo o que deve sair no DOU de {format_date_pt(reference_date)}.')
        parts.extend(_items_block_text(items))
    parts.append(_SIGNATURE_TEXT)
    return '\n\n'.join(parts)


def render_pubdou_html(items: list[dict], terms: list[str], reference_date, now: datetime) -> str:
    body = [f'<p style="margin:0 0 12px">Prezados, {greeting(now)}!</p>']
    if not items:
        body.append(
            f'<p style="margin:0 0 16px">Não tivemos publicações previstas para o DOU de '
            f'{html_lib.escape(format_date_pt(reference_date))}.</p>'
        )
    else:
        body.append(
            f'<p style="margin:0 0 16px">Encaminho abaixo o que deve sair no DOU de '
            f'{html_lib.escape(format_date_pt(reference_date))}.</p>'
        )
        body.extend(_items_block_html(items, terms))
    body.append(f'<p style="margin:4px 0 0">{_SIGNATURE_TEXT}</p>')
    return _wrap_email_html(body)


_PUBDOU_INTRO = 'Informo que todos os andamentos abaixo foram devidamente publicados no DOU de hoje.'
_PUBDOU_INTRO_EXCEPT = (
    'Informo que todos os andamentos abaixo foram devidamente publicados no DOU de hoje, exceto {missing}.'
)
_PUBDOU_INTRO_ONE = 'Informo que o andamento abaixo foi devidamente publicado no DOU de hoje.'
_PUBDOU_INTRO_ONE_EXCEPT = (
    'Informo que o andamento abaixo foi devidamente publicado no DOU de hoje, exceto {missing}.'
)


def _pubdou_intro(missing: list[str], single: bool) -> str:
    if missing:
        template = _PUBDOU_INTRO_ONE_EXCEPT if single else _PUBDOU_INTRO_EXCEPT
        return template.format(missing='; '.join(missing))
    return _PUBDOU_INTRO_ONE if single else _PUBDOU_INTRO


def render_confirmation_text(items: list[dict], missing: list[str], nothing_published: bool, single: bool) -> str:
    """Confirmação da manhã (User Story 3) — 'exceto ...' quando algo antecipado não
    saiu; `single` reflete a concordância pelo total de itens ANTECIPADOS na véspera
    (não pelos confirmados — um único item antecipado que não saiu continua sendo
    "o andamento abaixo", no singular, mesmo com `items` vazio); aviso curto
    específico quando o DOU real do dia não teve NENHUMA publicação do CADE
    (`nothing_published`) — distinto de "nada bateu com o que este assinante
    antecipou" (`items` vazio com `nothing_published=False`), que ainda lista o
    'exceto' normalmente em vez do aviso de dia sem publicação nenhuma."""
    if nothing_published:
        return '\n\n'.join(['Prezados, bom dia.', 'Não tivemos publicações no DOU de hoje.', _SIGNATURE_TEXT])
    parts = ['Prezados, bom dia.', _pubdou_intro(missing, single)]
    parts.extend(_items_block_text(items))
    parts.append(_SIGNATURE_TEXT)
    return '\n\n'.join(parts)


def render_confirmation_html(
    items: list[dict], missing: list[str], terms: list[str], nothing_published: bool, single: bool,
) -> str:
    if nothing_published:
        return _wrap_email_html([
            '<p style="margin:0 0 12px">Prezados, bom dia.</p>',
            '<p style="margin:0 0 16px">Não tivemos publicações no DOU de hoje.</p>',
            f'<p style="margin:4px 0 0">{_SIGNATURE_TEXT}</p>',
        ])
    body = [
        '<p style="margin:0 0 12px">Prezados, bom dia.</p>',
        f'<p style="margin:0 0 16px">{html_lib.escape(_pubdou_intro(missing, single))}</p>',
    ]
    body.extend(_items_block_html(items, terms))
    body.append(f'<p style="margin:4px 0 0">{_SIGNATURE_TEXT}</p>')
    return _wrap_email_html(body)

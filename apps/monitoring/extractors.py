"""
Extração e normalização de texto de páginas HTML públicas do CADE/SEI.

Este módulo é puramente funcional — sem efeitos colaterais, sem acesso ao banco.
Portado e refatorado a partir de cademon/scraper.py.

Responsabilidades:
  - Parsear HTML e extrair texto visível (VisibleTextParser, LinkTextParser)
  - Normalizar texto: remover espaço extra, ruído de timestamp, etc.
  - Calcular hash determinístico SHA-256
  - Extrair registros estruturados do CADE/SEI (andamentos, protocolos)
  - Identificar novos registros comparando com texto anterior
"""
from __future__ import annotations

import hashlib
import html as html_lib
import re
import unicodedata
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Constantes CADE/SEI
# ---------------------------------------------------------------------------

CADE_SEARCH_URL = (
    'https://sei.cade.gov.br/sei/modulos/pesquisa/md_pesq_processo_pesquisar.php'
    '?acao_externa=protocolo_pesquisar&acao_origem_externa=protocolo_pesquisar'
    '&id_orgao_acesso_externo=0'
)

BLOCK_TAGS = {
    'address', 'article', 'aside', 'blockquote', 'br', 'caption', 'dd', 'div', 'dl', 'dt',
    'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'tbody', 'td',
    'tfoot', 'th', 'thead', 'tr', 'ul',
}
SKIP_TAGS = {'script', 'style', 'noscript', 'template', 'svg'}

DATE_TIME_RE = re.compile(r'^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$')
DATE_RE = re.compile(r'^\d{2}/\d{2}/\d{4}$')
PROCESS_OR_DOCUMENT_RE = re.compile(r'^(\d+|\d{5}\.\d{6}/\d{4}-\d{2})$')
DOCUMENT_NUMBER_RE = re.compile(r'^\d{5,}$')
PROCESS_DETAIL_LINK_RE = re.compile(
    r"href=[\"']([^\"']*md_pesq_processo_exibir\.php\?[^\"']+)", re.I
)

DOCUMENT_LINK_MARKERS = (
    'md_pesq_documento_consulta_externa.php',
    'documento_consulta_externa',
    'documento_download_anexo',
    'controlador.php?acao=documento',
)

PROTOCOL_HEADER_KEYS = {
    'documento / processo', 'documento', 'processo',
    'tipo de documento', 'data do documento',
    'data de registro', 'unidade',
}
MOVEMENT_HEADER_KEYS = {'data/hora', 'data hora', 'unidade', 'descricao'}

# Padrões de linhas que variam a cada carregamento (timestamps do servidor)
# e que geram falsos positivos se não forem removidos.
NOISE_PATTERNS = [
    re.compile(r'^data/hora\s+da\s+consulta\b.*$', re.I),
    re.compile(r'^hora\s+da\s+consulta\b.*$', re.I),
    re.compile(r'^consulta\s+realizada\s+em\b.*$', re.I),
    re.compile(r'^pagina\s+gerada\s+em\b.*$', re.I),
    re.compile(r'^pÃ¡gina\s+gerada\s+em\b.*$', re.I),
    re.compile(r'^tempo\s+de\s+geracao\b.*$', re.I),
    re.compile(r'^tempo\s+de\s+geraÃ§Ã£o\b.*$', re.I),
]

# ---------------------------------------------------------------------------
# Parsers HTML
# ---------------------------------------------------------------------------


class VisibleTextParser(HTMLParser):
    """
    Extrai somente o texto visível de um HTML.
    Ignora scripts, estilos, SVGs e elementos ocultos.
    Insere quebras de linha em elementos block para preservar estrutura.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth: int = 0
        self.title_parts: list[str] = []
        self.in_title: bool = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag == 'title':
            self.in_title = True
        if tag in BLOCK_TAGS and not self.skip_depth:
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == 'title':
            self.in_title = False
        if tag in BLOCK_TAGS and not self.skip_depth:
            self.parts.append('\n')

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        self.parts.append(data)

    @property
    def title(self) -> str:
        return normalize_text(' '.join(self.title_parts), drop_noise=False)[:200]

    @property
    def text(self) -> str:
        return normalize_text(''.join(self.parts), drop_noise=True)


class LinkTextParser(HTMLParser):
    """Extrai todos os links (<a href>) com seus textos e atributos."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.current_href: str = ''
        self.current_attrs: str = ''
        self.current_parts: list[str] = []
        self.anchor_depth: int = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != 'a':
            return
        href = ''
        attrs_text: list[str] = []
        for key, value in attrs:
            clean_value = value or ''
            attrs_text.append(f'{key}={clean_value}')
            if key.lower() == 'href' and clean_value:
                href = clean_value
        self.current_href = href
        self.current_attrs = ' '.join(attrs_text)
        self.current_parts = []
        self.anchor_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != 'a' or not self.anchor_depth:
            return
        self.anchor_depth -= 1
        if self.anchor_depth == 0:
            text = normalize_text(' '.join(self.current_parts), drop_noise=False)
            self.links.append({
                'href': self.current_href,
                'text': text,
                'attrs': self.current_attrs,
            })
            self.current_href = ''
            self.current_attrs = ''
            self.current_parts = []

    def handle_data(self, data: str) -> None:
        if self.anchor_depth:
            self.current_parts.append(data)


# ---------------------------------------------------------------------------
# Funções de normalização
# ---------------------------------------------------------------------------


def normalize_text(text: str, drop_noise: bool = True) -> str:
    """
    Normaliza texto extraído de HTML:
      - substitui &nbsp; por espaço
      - colapsa espaços horizontais múltiplos
      - remove linhas em branco
      - remove linhas de ruído (timestamps do servidor) se drop_noise=True
    """
    text = text.replace('\xa0', ' ')
    text = re.sub(r'[ \t\f\v]+', ' ', text)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if drop_noise and any(p.match(line) for p in NOISE_PATTERNS):
            continue
        lines.append(line)
    return '\n'.join(lines).strip()


def html_to_text(html: str) -> tuple[str, str]:
    """Converte HTML em (texto_visível_normalizado, título_da_página)."""
    parser = VisibleTextParser()
    parser.feed(html)
    return parser.text, parser.title


def stable_hash(text: str) -> str:
    """Hash SHA-256 determinístico do texto normalizado."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def folded(value: str) -> str:
    """Normaliza string para comparação case-insensitive sem acentos."""
    normalized = unicodedata.normalize('NFKD', value.strip().lower())
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


# ---------------------------------------------------------------------------
# Extração estruturada CADE/SEI
# ---------------------------------------------------------------------------


def _relevant_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _section_lines(lines: list[str], section_key: str) -> list[str]:
    """Extrai linhas de uma seção identificada por section_key."""
    start = None
    for idx, line in enumerate(lines):
        if folded(line).startswith(section_key):
            start = idx + 1
            break
    if start is None:
        return []
    collected: list[str] = []
    for line in lines[start:]:
        key = folded(line)
        if key.startswith('lista de ') and not key.startswith(section_key):
            break
        collected.append(line)
    return collected


def _without_headers(lines: list[str], header_keys: set[str]) -> list[str]:
    return [line for line in lines if folded(line) not in header_keys]


def _br_date_key(value: str) -> str:
    """Converte data BR (DD/MM/AAAA HH:MM) em chave de ordenação (AAAAMMDDHHNN)."""
    match = re.match(r'^(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?$', value.strip())
    if not match:
        return ''
    day, month, year, hour, minute = match.groups()
    return f'{year}{month}{day}{hour or "00"}{minute or "00"}'


def extract_protocol_records(text: str) -> list[dict[str, str]]:
    """
    Extrai registros da Lista de Protocolos do CADE/SEI.
    Retorna lista de dicts com: kind, sort_key, document, doc_type, etc.
    """
    cells = _without_headers(
        _section_lines(_relevant_lines(text), 'lista de protocolos'),
        PROTOCOL_HEADER_KEYS,
    )
    records: list[dict[str, str]] = []
    i = 0
    while i + 4 < len(cells):
        doc, doc_type, doc_date, reg_date, unit = cells[i:i + 5]
        if (
            PROCESS_OR_DOCUMENT_RE.match(doc)
            and DATE_RE.match(doc_date)
            and DATE_RE.match(reg_date)
        ):
            records.append({
                'kind': 'documento',
                'sort_key': _br_date_key(reg_date),
                'document': doc,
                'doc_type': doc_type,
                'doc_date': doc_date,
                'registry_date': reg_date,
                'unit': unit,
                'text': (
                    f'Novo documento: {doc} | {doc_type} | '
                    f'Data do documento: {doc_date} | Registro: {reg_date} | Unidade: {unit}'
                ),
            })
            i += 5
            continue
        i += 1
    return records


def extract_movement_records(text: str) -> list[dict[str, str]]:
    """
    Extrai registros da Lista de Andamentos do CADE/SEI.
    Cada andamento tem: data/hora, unidade e descrição.
    """
    cells = _without_headers(
        _section_lines(_relevant_lines(text), 'lista de andamentos'),
        MOVEMENT_HEADER_KEYS,
    )
    records: list[dict[str, str]] = []
    i = 0
    while i < len(cells):
        if not DATE_TIME_RE.match(cells[i]) or i + 2 >= len(cells):
            i += 1
            continue
        event_date = cells[i]
        unit = cells[i + 1]
        i += 2
        desc_lines: list[str] = []
        while i < len(cells) and not DATE_TIME_RE.match(cells[i]):
            desc_lines.append(cells[i])
            i += 1
        description = ' '.join(desc_lines).strip()
        if description:
            records.append({
                'kind': 'andamento',
                'sort_key': _br_date_key(event_date),
                'text': f'Novo andamento: {event_date} | {unit} | {description}',
            })
    return records


def extract_cade_entries(text: str) -> dict[str, list[str]]:
    """Retorna todas as entradas estruturadas do texto (protocolos e andamentos)."""
    return {
        'protocols': [r['text'] for r in extract_protocol_records(text)],
        'movements': [r['text'] for r in extract_movement_records(text)],
    }


def new_protocol_records(old_text: str | None, new_text: str) -> list[dict[str, str]]:
    """Retorna apenas os registros de protocolo presentes em new_text mas não em old_text."""
    old_entries = {r['text'] for r in extract_protocol_records(old_text or '')}
    return [r for r in extract_protocol_records(new_text) if r['text'] not in old_entries]


def latest_cade_records(text: str | None, limit: int = 3) -> list[str]:
    """Retorna os registros mais recentes (andamentos + protocolos) ordenados por data."""
    if not text:
        return []
    records = extract_movement_records(text) + extract_protocol_records(text)
    records.sort(key=lambda r: r['sort_key'], reverse=True)
    return [r['text'] for r in records[:limit]]


def extract_process_detail_url(html: str) -> str | None:
    """Extrai a URL de detalhe do processo a partir da página de resultados da busca CADE/SEI."""
    import urllib.parse
    match = PROCESS_DETAIL_LINK_RE.search(html)
    if not match:
        return None
    href = html_lib.unescape(match.group(1))
    return urllib.parse.urljoin(CADE_SEARCH_URL, href)

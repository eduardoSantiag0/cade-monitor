from __future__ import annotations

import hashlib
import html as html_lib
import mimetypes
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

from .utils import looks_like_url, utcnow_iso


CADE_SEARCH_URL = 'https://sei.cade.gov.br/sei/modulos/pesquisa/md_pesq_processo_pesquisar.php?acao_externa=protocolo_pesquisar&acao_origem_externa=protocolo_pesquisar&id_orgao_acesso_externo=0'

BLOCK_TAGS = {
    'address', 'article', 'aside', 'blockquote', 'br', 'caption', 'dd', 'div', 'dl', 'dt',
    'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'tbody', 'td',
    'tfoot', 'th', 'thead', 'tr', 'ul'
}
SKIP_TAGS = {'script', 'style', 'noscript', 'template', 'svg'}
PROCESS_DETAIL_LINK_RE = re.compile(r"href=[\"']([^\"']*md_pesq_processo_exibir\.php\?[^\"']+)", re.I)
DOCUMENT_NUMBER_RE = re.compile(r'^\d{5,}$')
DOCUMENT_LINK_MARKERS = (
    'md_pesq_documento_consulta_externa.php',
    'documento_consulta_externa',
    'documento_download_anexo',
    'controlador.php?acao=documento',
)
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
DATE_TIME_RE = re.compile(r'^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$')
DATE_RE = re.compile(r'^\d{2}/\d{2}/\d{4}$')
PROCESS_OR_DOCUMENT_RE = re.compile(r'^(\d+|\d{5}\.\d{6}/\d{4}-\d{2})$')
PROTOCOL_HEADER_KEYS = {
    'documento / processo',
    'documento',
    'processo',
    'tipo de documento',
    'data do documento',
    'data de registro',
    'unidade',
}
MOVEMENT_HEADER_KEYS = {'data/hora', 'data hora', 'unidade', 'descricao'}
NOISE_PATTERNS = [
    re.compile(r'^data/hora\s+da\s+consulta\b.*$', re.I),
    re.compile(r'^hora\s+da\s+consulta\b.*$', re.I),
    re.compile(r'^consulta\s+realizada\s+em\b.*$', re.I),
    re.compile(r'^pagina\s+gerada\s+em\b.*$', re.I),
    re.compile(r'^pÃ¡gina\s+gerada\s+em\b.*$', re.I),
    re.compile(r'^tempo\s+de\s+geracao\b.*$', re.I),
    re.compile(r'^tempo\s+de\s+geraÃ§Ã£o\b.*$', re.I),
]


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    url: str
    status_code: int
    title: str
    text: str
    hash: str
    fetched_at: str
    content_length: int
    html: str = ''


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False

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
        return normalize_plain_text(' '.join(self.title_parts), drop_noise=False)[:200]

    @property
    def text(self) -> str:
        return normalize_plain_text(''.join(self.parts), drop_noise=True)


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.current_href = ''
        self.current_attrs = ''
        self.current_parts: list[str] = []
        self.anchor_depth = 0

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
            text = normalize_plain_text(' '.join(self.current_parts), drop_noise=False)
            self.links.append({'href': self.current_href, 'text': text, 'attrs': self.current_attrs})
            self.current_href = ''
            self.current_attrs = ''
            self.current_parts = []

    def handle_data(self, data: str) -> None:
        if self.anchor_depth:
            self.current_parts.append(data)


def is_url_source(source: str) -> bool:
    return looks_like_url(source)


def normalize_plain_text(text: str, drop_noise: bool = True) -> str:
    text = text.replace('\xa0', ' ')
    text = re.sub(r'[ \t\f\v]+', ' ', text)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if drop_noise and any(pattern.match(line) for pattern in NOISE_PATTERNS):
            continue
        lines.append(line)
    return '\n'.join(lines).strip()


def normalize_html(html: str) -> tuple[str, str]:
    parser = VisibleTextParser()
    parser.feed(html)
    return parser.text, parser.title


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def folded(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value.strip().lower())
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def relevant_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def section_lines(lines: list[str], section_key: str) -> list[str]:
    start = None
    for index, line in enumerate(lines):
        key = folded(line)
        if key.startswith(section_key):
            start = index + 1
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


def without_headers(lines: list[str], header_keys: set[str]) -> list[str]:
    return [line for line in lines if folded(line) not in header_keys]


def br_date_key(value: str) -> str:
    match = re.match(r'^(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?$', value.strip())
    if not match:
        return ''
    day, month, year, hour, minute = match.groups()
    return f'{year}{month}{day}{hour or "00"}{minute or "00"}'


def extract_protocol_records(text: str) -> list[dict[str, str]]:
    cells = without_headers(section_lines(relevant_lines(text), 'lista de protocolos'), PROTOCOL_HEADER_KEYS)
    records: list[dict[str, str]] = []
    index = 0
    while index + 4 < len(cells):
        document, doc_type, doc_date, registry_date, unit = cells[index:index + 5]
        if PROCESS_OR_DOCUMENT_RE.match(document) and DATE_RE.match(doc_date) and DATE_RE.match(registry_date):
            records.append({
                'kind': 'documento',
                'sort_key': br_date_key(registry_date),
                'document': document,
                'doc_type': doc_type,
                'doc_date': doc_date,
                'registry_date': registry_date,
                'unit': unit,
                'text': (
                    f'Novo documento: {document} | {doc_type} | '
                    f'Data do documento: {doc_date} | Registro: {registry_date} | Unidade: {unit}'
                ),
            })
            index += 5
            continue
        index += 1
    return records


def extract_movement_records(text: str) -> list[dict[str, str]]:
    cells = without_headers(section_lines(relevant_lines(text), 'lista de andamentos'), MOVEMENT_HEADER_KEYS)
    records: list[dict[str, str]] = []
    index = 0
    while index < len(cells):
        if not DATE_TIME_RE.match(cells[index]) or index + 2 >= len(cells):
            index += 1
            continue
        event_date = cells[index]
        unit = cells[index + 1]
        index += 2
        description_lines: list[str] = []
        while index < len(cells) and not DATE_TIME_RE.match(cells[index]):
            description_lines.append(cells[index])
            index += 1
        description = ' '.join(description_lines).strip()
        if description:
            records.append({
                'kind': 'andamento',
                'sort_key': br_date_key(event_date),
                'text': f'Novo andamento: {event_date} | {unit} | {description}',
            })
    return records


def extract_protocol_entries(text: str) -> list[str]:
    return [record['text'] for record in extract_protocol_records(text)]


def new_protocol_records(old_text: str | None, new_text: str) -> list[dict[str, str]]:
    old_entries = {record['text'] for record in extract_protocol_records(old_text or '')}
    return [record for record in extract_protocol_records(new_text) if record['text'] not in old_entries]


def looks_like_document_url(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in DOCUMENT_LINK_MARKERS)


def candidate_document_url(value: str, base_url: str) -> str | None:
    value = html_lib.unescape(value or '').strip()
    if not value:
        return None

    candidates: list[str] = []
    for marker in DOCUMENT_LINK_MARKERS:
        marker_pattern = re.escape(marker)
        candidates.extend(re.findall(rf'["\']([^"\']*{marker_pattern}[^"\']*)["\']', value, flags=re.I))
        candidates.extend(re.findall(rf'(?:^|[\s(=])([^\s"\'<>)]*{marker_pattern}[^\s"\'<>)]*)', value, flags=re.I))

    is_plain_url = not re.search(r'\s|\bhref\s*=|\bon\w+\s*=|\btitle\s*=|\balt\s*=', value, flags=re.I)
    if is_plain_url and looks_like_document_url(value):
        candidates.insert(0, value)

    for candidate in candidates:
        candidate = candidate.strip(' "\'();')
        if not candidate or candidate.startswith('#'):
            continue
        if candidate.lower().startswith('javascript:'):
            continue
        if looks_like_document_url(candidate):
            return urllib.parse.urljoin(base_url, candidate)
    return None


def candidate_document_urls(fragment: str, base_url: str) -> list[str]:
    urls: list[str] = []
    raw_values = re.findall(r'''(?:href|onclick|data-url|data-href)=(["'])(.*?)\1''', fragment, flags=re.I | re.S)
    for _, raw_value in raw_values:
        url = candidate_document_url(raw_value, base_url)
        if url and url not in urls:
            urls.append(url)
    for marker in DOCUMENT_LINK_MARKERS:
        marker_pattern = re.escape(marker)
        for raw_value in re.findall(rf'[^\s"\'<>)]*{marker_pattern}[^\s"\'<>)]*', fragment, flags=re.I):
            url = candidate_document_url(raw_value, base_url)
            if url and url not in urls:
                urls.append(url)
    return urls


def extract_document_links(html: str, base_url: str) -> dict[str, str]:
    parser = LinkTextParser()
    parser.feed(html or '')
    links: dict[str, str] = {}

    for link in parser.links:
        combined = ' '.join([link.get('text', ''), link.get('href', ''), link.get('attrs', '')])
        numbers = re.findall(r'\b\d{5,}\b', combined)
        url = candidate_document_url(link.get('href', ''), base_url) or candidate_document_url(link.get('attrs', ''), base_url)
        if not url:
            continue
        for document_number in numbers:
            links.setdefault(document_number, url)

    for row_match in re.finditer(r'<tr\b.*?</tr>', html or '', flags=re.I | re.S):
        row_html = row_match.group(0)
        row_text, _ = normalize_html(row_html)
        numbers = re.findall(r'\b\d{5,}\b', row_text)
        urls = candidate_document_urls(row_html, base_url)
        if not numbers or not urls:
            continue
        for document_number in numbers:
            links.setdefault(document_number, urls[0])

    return links


def safe_document_filename(document: str, doc_type: str, content_type: str, fallback_url: str) -> str:
    base = f'{document}-{doc_type}'.strip('-') or document or 'documento'
    base = unicodedata.normalize('NFKD', base)
    base = ''.join(ch for ch in base if not unicodedata.combining(ch))
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', base).strip('._-') or 'documento'
    extension = mimetypes.guess_extension(content_type.split(';', 1)[0].strip()) or ''
    url_path = urllib.parse.urlparse(fallback_url).path
    url_extension = urllib.parse.unquote(url_path.rsplit('/', 1)[-1]).rsplit('.', 1)
    if len(url_extension) == 2 and not extension:
        extension = '.' + re.sub(r'[^A-Za-z0-9]+', '', url_extension[1])[:8]
    if extension and not base.lower().endswith(extension.lower()):
        base += extension
    return base[:140]


def download_document_attachment(url: str, record: dict[str, str], timeout: int, user_agent: str, max_bytes: int = MAX_DOCUMENT_BYTES) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': user_agent,
            'Accept': 'application/pdf,text/html,application/xhtml+xml,application/octet-stream,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
            'Referer': CADE_SEARCH_URL,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, 'status', 200))
            if not 200 <= status < 300:
                raise FetchError(f'HTTP {status} ao baixar documento {record.get("document", "")}')
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise FetchError(f'Documento {record.get("document", "")} excede {max_bytes // (1024 * 1024)} MB')
            content_type = response.headers.get_content_type() or 'application/octet-stream'
    except urllib.error.HTTPError as exc:
        raise FetchError(f'HTTP {exc.code} ao baixar documento {record.get("document", "")}') from exc
    except urllib.error.URLError as exc:
        raise FetchError(f'Falha de rede ao baixar documento {record.get("document", "")}: {exc.reason}') from exc
    except TimeoutError as exc:
        raise FetchError(f'Tempo esgotado ao baixar documento {record.get("document", "")}') from exc

    filename = safe_document_filename(record.get('document', ''), record.get('doc_type', ''), content_type, url)
    return {
        'document': record.get('document', ''),
        'title': record.get('doc_type', ''),
        'filename': filename,
        'content_type': content_type,
        'content': content,
        'url': url,
    }


def collect_new_document_attachments(old_text: str | None, snapshot: Snapshot, timeout: int, user_agent: str, limit: int = 3) -> tuple[list[dict[str, object]], list[str]]:
    records = [record for record in new_protocol_records(old_text, snapshot.text) if DOCUMENT_NUMBER_RE.match(record.get('document', ''))]
    if not records:
        return [], []
    links = extract_document_links(snapshot.html, snapshot.url)
    attachments: list[dict[str, object]] = []
    errors: list[str] = []
    for record in records[:limit]:
        document = record.get('document', '')
        url = links.get(document)
        if not url:
            errors.append(f'Documento {document}: link de download nao encontrado na pagina publica.')
            continue
        try:
            attachments.append(download_document_attachment(url, record, timeout, user_agent))
        except FetchError as exc:
            errors.append(str(exc))
    remaining = len(records) - limit
    if remaining > 0:
        errors.append(f'{remaining} documento(s) novo(s) nao baixado(s) pelo limite de anexos por alerta.')
    return attachments, errors


def extract_movement_entries(text: str) -> list[str]:
    return [record['text'] for record in extract_movement_records(text)]


def latest_cade_records(text: str | None, limit: int = 3) -> list[str]:
    if not text:
        return []
    records = extract_movement_records(text) + extract_protocol_records(text)
    records.sort(key=lambda item: item['sort_key'], reverse=True)
    return [record['text'] for record in records[:limit]]


def extract_cade_entries(text: str) -> dict[str, list[str]]:
    return {
        'protocols': extract_protocol_entries(text),
        'movements': extract_movement_entries(text),
    }


def structured_cade_diff(old_text: str | None, new_text: str, max_items: int = 12) -> tuple[str, str] | None:
    old_entries = extract_cade_entries(old_text or '')
    new_entries = extract_cade_entries(new_text)

    old_protocols = set(old_entries['protocols'])
    old_movements = set(old_entries['movements'])
    added_movements = [entry for entry in new_entries['movements'] if entry not in old_movements]
    added_protocols = [entry for entry in new_entries['protocols'] if entry not in old_protocols]

    if not added_movements and not added_protocols:
        return None

    summary_lines: list[str] = []
    detail_lines: list[str] = []
    if added_movements:
        summary_lines.append(f'{len(added_movements)} novo(s) andamento(s) detectado(s).')
        detail_lines.append('Andamentos novos:')
        detail_lines.extend(added_movements[:max_items])
    if added_protocols:
        summary_lines.append(f'{len(added_protocols)} novo(s) documento(s)/protocolo(s) detectado(s).')
        if detail_lines:
            detail_lines.append('')
        detail_lines.append('Documentos/protocolos novos:')
        detail_lines.extend(added_protocols[:max_items])

    hidden = max(0, len(added_movements) - max_items) + max(0, len(added_protocols) - max_items)
    if hidden:
        detail_lines.append(f'... mais {hidden} registro(s) novo(s).')

    highlighted = (added_movements + added_protocols)[:max_items]
    summary = '\n'.join(summary_lines + highlighted)
    return summary[:4000], '\n'.join(detail_lines)[:8000]


def fetch_snapshot(source: str, timeout: int, user_agent: str) -> Snapshot:
    source = source.strip()
    if is_url_source(source):
        return fetch_url_snapshot(source, timeout, user_agent)
    return fetch_cade_search_snapshot(source, timeout, user_agent)


def fetch_url_snapshot(url: str, timeout: int, user_agent: str) -> Snapshot:
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
        },
    )
    raw, status, charset = open_request(request, timeout)
    return snapshot_from_html(url, raw, status, charset)


def fetch_cade_search_snapshot(process_number: str, timeout: int, user_agent: str) -> Snapshot:
    payload = {
        'txtProtocoloPesquisa': process_number.strip(),
        'q': '',
        'chkSinProcessos': 'P',
        'chkSinDocumentosGerados': 'G',
        'chkSinDocumentosRecebidos': 'R',
        'txtParticipante': '',
        'hdnIdParticipante': '',
        'txtUnidade': '',
        'hdnIdUnidade': '',
        'selTipoProcedimentoPesquisa': '',
        'selSeriePesquisa': '',
        'txtDataInicio': '',
        'txtDataFim': '',
        'txtNumeroDocumentoPesquisa': '',
        'txtAssinante': '',
        'hdnIdAssinante': '',
        'txtDescricaoPesquisa': '',
        'txtAssunto': '',
        'hdnIdAssunto': '',
        'hdnSiglasUsuarios': '',
        'partialfields': '',
        'requiredfields': '',
        'as_q': '',
        'click': '0',
        'hdnFlagPesquisa': '1',
        'sbmPesquisar': 'Pesquisar',
    }
    data = urllib.parse.urlencode(payload).encode('utf-8')
    request = urllib.request.Request(
        CADE_SEARCH_URL,
        data=data,
        method='POST',
        headers={
            'User-Agent': user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
            'Origin': 'https://sei.cade.gov.br',
            'Referer': CADE_SEARCH_URL,
        },
    )
    raw, status, charset = open_request(request, timeout)
    html = raw.decode(charset, errors='replace')
    detail_url = extract_process_detail_url(html)
    if detail_url:
        return fetch_url_snapshot(detail_url, timeout, user_agent)
    return snapshot_from_html(CADE_SEARCH_URL, raw, status, charset, prefix=f'Pesquisa CADE: {process_number.strip()}')


def extract_process_detail_url(html: str) -> str | None:
    match = PROCESS_DETAIL_LINK_RE.search(html)
    if not match:
        return None
    href = html_lib.unescape(match.group(1))
    return urllib.parse.urljoin(CADE_SEARCH_URL, href)


def open_request(request: urllib.request.Request, timeout: int) -> tuple[bytes, int, str]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, 'status', 200))
            raw = response.read()
            charset = response.headers.get_content_charset() or 'utf-8'
            return raw, status, charset
    except urllib.error.HTTPError as exc:
        raise FetchError(f'HTTP {exc.code} ao acessar a pagina publica') from exc
    except urllib.error.URLError as exc:
        raise FetchError(f'Falha de rede ao acessar a pagina publica: {exc.reason}') from exc
    except TimeoutError as exc:
        raise FetchError('Tempo esgotado ao acessar a pagina publica') from exc


def snapshot_from_html(url: str, raw: bytes, status: int, charset: str, prefix: str = '') -> Snapshot:
    html = raw.decode(charset, errors='replace')
    text, title = normalize_html(html)
    if prefix:
        text = prefix + '\n' + text
    if not text.strip():
        raise FetchError('A pagina foi carregada, mas nao foi possivel extrair texto util.')
    return Snapshot(
        url=url,
        status_code=status,
        title=title,
        text=text,
        hash=stable_hash(text),
        fetched_at=utcnow_iso(),
        content_length=len(raw),
        html=html,
    )


def diff_summary(old_text: str | None, new_text: str, max_lines: int = 12) -> tuple[str, str]:
    structured = structured_cade_diff(old_text, new_text, max_lines)
    if structured:
        return structured

    old_lines = [line for line in (old_text or '').splitlines() if line.strip()]
    new_lines = [line for line in new_text.splitlines() if line.strip()]
    old_set = set(old_lines)
    new_set = set(new_lines)
    added = [line for line in new_lines if line not in old_set]
    removed = [line for line in old_lines if line not in new_set]

    if added:
        summary = 'Novas linhas detectadas:\n' + '\n'.join(added[:max_lines])
        if len(added) > max_lines:
            summary += f'\n... mais {len(added) - max_lines} linha(s).'
    else:
        summary = 'A pagina mudou, mas nao foram identificadas linhas novas isoladas.'

    diff_lines: list[str] = []
    if added:
        diff_lines.append('Adicionado:')
        diff_lines.extend(f'+ {line}' for line in added[:max_lines])
    if removed:
        diff_lines.append('Removido:')
        diff_lines.extend(f'- {line}' for line in removed[:max_lines])
    if not diff_lines:
        diff_lines.append(summary)
    return summary[:4000], '\n'.join(diff_lines)[:8000]

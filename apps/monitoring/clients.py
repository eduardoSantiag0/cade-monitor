"""
Cliente HTTP para busca de snapshots de páginas públicas.

Responsabilidades:
  - Fazer requisições HTTP seguras (timeout, user-agent identificável)
  - Detectar e resolver URLs de processos CADE/SEI a partir de número de protocolo
  - Baixar documentos públicos como anexos
  - Não conter regra de negócio do sistema

Portado e refatorado a partir de cademon/scraper.py.
"""
from __future__ import annotations

import mimetypes
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .extractors import (
    CADE_SEARCH_URL,
    DOCUMENT_LINK_MARKERS,
    DOCUMENT_NUMBER_RE,
    LinkTextParser,
    extract_process_detail_url,
    html_to_text,
    new_protocol_records,
    normalize_text,
    stable_hash,
)

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024  # 8 MB por documento


class FetchError(RuntimeError):
    """Erro ao acessar uma página pública ou baixar um documento."""


@dataclass(frozen=True)
class Snapshot:
    """
    Resultado imutável de uma busca de página.
    Contém texto normalizado, hash e metadados — sem o HTML bruto
    (exceto quando necessário para extração de links de documentos).
    """

    url: str
    status_code: int
    title: str
    text: str
    content_hash: str
    fetched_at: str
    content_length: int
    html: str = field(default='', repr=False)


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def get_snapshot(source: str, timeout: int, user_agent: str) -> Snapshot:
    """
    Ponto de entrada principal.
    Aceita URL pública (http/https) ou número de processo CADE/SEI.
    Se for número, realiza a pesquisa pública e redireciona para o detalhe.
    """
    source = source.strip()
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in ('http', 'https') and parsed.netloc:
        return _fetch_url(source, timeout, user_agent)
    return _fetch_by_process_number(source, timeout, user_agent)


def resolve_process_url(process_number: str, timeout: int, user_agent: str) -> str | None:
    """
    Tenta resolver um número de processo para a URL pública de detalhe.
    Retorna None se não encontrar (processo não público ou número inválido).
    """
    try:
        raw, _, charset = _open_request(
            _build_search_request(process_number.strip(), user_agent),
            timeout,
        )
        html = raw.decode(charset, errors='replace')
        return extract_process_detail_url(html)
    except FetchError:
        return None


# ---------------------------------------------------------------------------
# Funções privadas de fetch
# ---------------------------------------------------------------------------


def _fetch_url(url: str, timeout: int, user_agent: str) -> Snapshot:
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
        },
    )
    raw, status, charset = _open_request(request, timeout)
    return _build_snapshot(url, raw, status, charset)


def _fetch_by_process_number(process_number: str, timeout: int, user_agent: str) -> Snapshot:
    raw, status, charset = _open_request(_build_search_request(process_number, user_agent), timeout)
    html = raw.decode(charset, errors='replace')
    detail_url = extract_process_detail_url(html)
    if detail_url:
        return _fetch_url(detail_url, timeout, user_agent)
    # Fallback: retorna o próprio resultado da pesquisa (processo pode não ser público)
    return _build_snapshot(
        CADE_SEARCH_URL,
        raw,
        status,
        charset,
        prefix=f'Pesquisa CADE: {process_number.strip()}',
    )


def _build_search_request(process_number: str, user_agent: str) -> urllib.request.Request:
    payload = {
        'txtProtocoloPesquisa': process_number.strip(),
        'q': '', 'chkSinProcessos': 'P',
        'chkSinDocumentosGerados': 'G', 'chkSinDocumentosRecebidos': 'R',
        'txtParticipante': '', 'hdnIdParticipante': '',
        'txtUnidade': '', 'hdnIdUnidade': '',
        'selTipoProcedimentoPesquisa': '', 'selSeriePesquisa': '',
        'txtDataInicio': '', 'txtDataFim': '',
        'txtNumeroDocumentoPesquisa': '', 'txtAssinante': '', 'hdnIdAssinante': '',
        'txtDescricaoPesquisa': '', 'txtAssunto': '', 'hdnIdAssunto': '',
        'hdnSiglasUsuarios': '', 'partialfields': '', 'requiredfields': '',
        'as_q': '', 'click': '0', 'hdnFlagPesquisa': '1',
        'sbmPesquisar': 'Pesquisar',
    }
    data = urllib.parse.urlencode(payload).encode('utf-8')
    return urllib.request.Request(
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


def _open_request(request: urllib.request.Request, timeout: int) -> tuple[bytes, int, str]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, 'status', 200))
            raw = response.read()
            charset = response.headers.get_content_charset() or 'utf-8'
            return raw, status, charset
    except urllib.error.HTTPError as exc:
        raise FetchError(f'HTTP {exc.code} ao acessar a página pública') from exc
    except urllib.error.URLError as exc:
        raise FetchError(f'Falha de rede: {exc.reason}') from exc
    except TimeoutError:
        raise FetchError('Tempo esgotado ao acessar a página pública')


def _build_snapshot(url: str, raw: bytes, status: int, charset: str, prefix: str = '') -> Snapshot:
    html = raw.decode(charset, errors='replace')
    text, title = html_to_text(html)
    if prefix:
        text = prefix + '\n' + text
    if not text.strip():
        raise FetchError('A página foi carregada, mas não foi possível extrair texto útil.')
    return Snapshot(
        url=url,
        status_code=status,
        title=title,
        text=text,
        content_hash=stable_hash(text),
        fetched_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        content_length=len(raw),
        html=html,
    )


# ---------------------------------------------------------------------------
# Download de documentos públicos
# ---------------------------------------------------------------------------


def _looks_like_document_url(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in DOCUMENT_LINK_MARKERS)


def _candidate_document_url(value: str, base_url: str) -> str | None:
    import html as html_lib
    value = html_lib.unescape(value or '').strip()
    if not value:
        return None
    candidates: list[str] = []
    for marker in DOCUMENT_LINK_MARKERS:
        mp = re.escape(marker)
        candidates.extend(re.findall(rf'["\']([^"\']*{mp}[^"\']*)["\']', value, flags=re.I))
        candidates.extend(re.findall(rf'(?:^|[\s(=])([^\s"\'<>)]*{mp}[^\s"\'<>)]*)', value, flags=re.I))
    if not re.search(r'\s|\bhref\s*=|\bon\w+\s*=|\btitle\s*=|\balt\s*=', value, flags=re.I):
        if _looks_like_document_url(value):
            candidates.insert(0, value)
    for candidate in candidates:
        candidate = candidate.strip(' "\'();')
        if not candidate or candidate.startswith('#') or candidate.lower().startswith('javascript:'):
            continue
        if _looks_like_document_url(candidate):
            return urllib.parse.urljoin(base_url, candidate)
    return None


def _candidate_document_urls(fragment: str, base_url: str) -> list[str]:
    urls: list[str] = []
    for _, raw_value in re.findall(
        r'''(?:href|onclick|data-url|data-href)=(["'])(.*?)\1''', fragment, flags=re.I | re.S
    ):
        url = _candidate_document_url(raw_value, base_url)
        if url and url not in urls:
            urls.append(url)
    for marker in DOCUMENT_LINK_MARKERS:
        mp = re.escape(marker)
        for raw_value in re.findall(rf'[^\s"\'<>)]*{mp}[^\s"\'<>)]*', fragment, flags=re.I):
            url = _candidate_document_url(raw_value, base_url)
            if url and url not in urls:
                urls.append(url)
    return urls


def extract_document_links(html_content: str, base_url: str) -> dict[str, str]:
    """Mapeia número_documento → URL_download para todos os links da página."""
    parser = LinkTextParser()
    parser.feed(html_content or '')
    links: dict[str, str] = {}

    for link in parser.links:
        combined = ' '.join([link.get('text', ''), link.get('href', ''), link.get('attrs', '')])
        numbers = re.findall(r'\b\d{5,}\b', combined)
        url = (
            _candidate_document_url(link.get('href', ''), base_url)
            or _candidate_document_url(link.get('attrs', ''), base_url)
        )
        if url:
            for num in numbers:
                links.setdefault(num, url)

    for row_match in re.finditer(r'<tr\b.*?</tr>', html_content or '', flags=re.I | re.S):
        row_html = row_match.group(0)
        row_text, _ = html_to_text(row_html)
        numbers = re.findall(r'\b\d{5,}\b', row_text)
        urls = _candidate_document_urls(row_html, base_url)
        if numbers and urls:
            for num in numbers:
                links.setdefault(num, urls[0])

    return links


def _safe_document_filename(document: str, doc_type: str, content_type: str, fallback_url: str) -> str:
    base = f'{document}-{doc_type}'.strip('-') or document or 'documento'
    base = unicodedata.normalize('NFKD', base)
    base = ''.join(ch for ch in base if not unicodedata.combining(ch))
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', base).strip('._-') or 'documento'
    extension = mimetypes.guess_extension(content_type.split(';', 1)[0].strip()) or ''
    url_path = urllib.parse.urlparse(fallback_url).path
    url_ext = urllib.parse.unquote(url_path.rsplit('/', 1)[-1]).rsplit('.', 1)
    if len(url_ext) == 2 and not extension:
        extension = '.' + re.sub(r'[^A-Za-z0-9]+', '', url_ext[1])[:8]
    if extension and not base.lower().endswith(extension.lower()):
        base += extension
    return base[:140]


def download_document(
    url: str,
    record: dict[str, str],
    timeout: int,
    user_agent: str,
) -> dict[str, object]:
    """Baixa um documento público e retorna seus metadados e conteúdo binário."""
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
            content = response.read(MAX_DOCUMENT_BYTES + 1)
            if len(content) > MAX_DOCUMENT_BYTES:
                raise FetchError(f'Documento excede {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB')
            content_type = response.headers.get_content_type() or 'application/octet-stream'
    except urllib.error.HTTPError as exc:
        raise FetchError(f'HTTP {exc.code} ao baixar documento {record.get("document", "")}') from exc
    except urllib.error.URLError as exc:
        raise FetchError(f'Falha de rede ao baixar documento: {exc.reason}') from exc
    except TimeoutError:
        raise FetchError(f'Tempo esgotado ao baixar documento {record.get("document", "")}')

    return {
        'document': record.get('document', ''),
        'title': record.get('doc_type', ''),
        'filename': _safe_document_filename(
            record.get('document', ''), record.get('doc_type', ''), content_type, url
        ),
        'content_type': content_type,
        'content': content,
        'url': url,
    }


def collect_new_documents(
    old_text: str | None,
    snapshot: Snapshot,
    timeout: int,
    user_agent: str,
    limit: int = 3,
) -> tuple[list[dict[str, object]], list[str]]:
    """
    Detecta novos documentos na Lista de Protocolos e tenta baixá-los como anexos.
    Só baixa documentos que NÃO existiam no snapshot anterior.
    """
    records = [
        r for r in new_protocol_records(old_text, snapshot.text)
        if DOCUMENT_NUMBER_RE.match(r.get('document', ''))
    ]
    if not records:
        return [], []

    links = extract_document_links(snapshot.html, snapshot.url)
    attachments: list[dict[str, object]] = []
    errors: list[str] = []

    for record in records[:limit]:
        doc_number = record.get('document', '')
        url = links.get(doc_number)
        if not url:
            errors.append(f'Documento {doc_number}: link de download não encontrado na página pública.')
            continue
        try:
            attachments.append(download_document(url, record, timeout, user_agent))
        except FetchError as exc:
            errors.append(str(exc))

    remaining = len(records) - limit
    if remaining > 0:
        errors.append(f'{remaining} documento(s) novo(s) não baixado(s) (limite de {limit} por alerta).')
    return attachments, errors

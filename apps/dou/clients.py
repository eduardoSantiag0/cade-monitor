"""
Cliente HTTP para as fontes externas do digest DOU (spec 009): Resenha do CADE
(sinc.cade.gov.br), listagem pública do DOU (in.gov.br) e publicações do SEI
(sei.cade.gov.br — o "boletim" usado pela antecipação da véspera).

Mesmo padrão de `apps/monitoring/clients.py`: stdlib `urllib`, headers explícitos,
retry/backoff herdado de `settings.REQUEST_RETRY_ATTEMPTS`/`REQUEST_RETRY_BACKOFF_SECONDS`.
`FetchError` é reaproveitada de `apps.monitoring.clients` (não duplicada aqui).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from django.conf import settings

from apps.monitoring.clients import FetchError

RESENHA_SOLR_URL = 'https://sinc.cade.gov.br/api/solr/documentos/select'
INGOV_LISTING_URL = 'https://www.in.gov.br/leiturajornal'
SEI_PUBLICATIONS_URL = (
    'https://sei.cade.gov.br/sei/publicacoes/controlador_publicacoes.php'
    '?acao=publicacao_pesquisar&acao_origem=publicacao_pesquisar&id_orgao_publicacao=0'
)

_DEFAULT_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
}


def _open_request(request: urllib.request.Request, timeout: int) -> tuple[bytes, int, str]:
    """Mesma política de retry/backoff de `apps.monitoring.clients._open_request`."""
    attempts = max(1, int(getattr(settings, 'REQUEST_RETRY_ATTEMPTS', 3)))
    backoff = float(getattr(settings, 'REQUEST_RETRY_BACKOFF_SECONDS', 1.5))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(getattr(response, 'status', 200))
                raw = response.read()
                charset = response.headers.get_content_charset() or 'utf-8'
                return raw, status, charset
        except urllib.error.HTTPError as exc:
            raise FetchError(f'HTTP {exc.code} ao acessar {request.full_url}') from exc
        except urllib.error.URLError as exc:
            last_error = exc
        except TimeoutError as exc:
            last_error = exc

        if attempt < attempts:
            time.sleep(backoff * attempt)

    if isinstance(last_error, urllib.error.URLError):
        raise FetchError(f'Falha de rede ao acessar {request.full_url}: {last_error.reason}') from last_error
    if isinstance(last_error, TimeoutError):
        raise FetchError(f'Tempo esgotado ao acessar {request.full_url}') from last_error
    raise FetchError(f'Falha ao acessar {request.full_url}')


def _get(url: str, timeout: int, user_agent: str) -> tuple[bytes, int, str]:
    request = urllib.request.Request(url, headers={**_DEFAULT_HEADERS, 'User-Agent': user_agent})
    return _open_request(request, timeout)


def fetch_resenha(reference_date: date, timeout: int, user_agent: str) -> dict | None:
    """Busca a Resenha do CADE (documento diário único, Solr público) para a data
    informada. Retorna `None` quando a edição do dia ainda não está disponível (não é
    erro); levanta `FetchError` em falha de rede/HTTP."""
    query = f'colecao:resenha_dou AND data_ordem:{reference_date.strftime("%Y%m%d")}'
    params = urllib.parse.urlencode({'q': query, 'fl': 'conteudo', 'rows': 1, 'wt': 'json'})
    raw, _status, charset = _get(f'{RESENHA_SOLR_URL}?{params}', timeout, user_agent)
    try:
        payload = json.loads(raw.decode(charset, errors='replace'))
    except json.JSONDecodeError as exc:
        raise FetchError(f'Resposta inesperada (não-JSON) da Resenha do CADE: {exc}') from exc
    docs = payload.get('response', {}).get('docs', [])
    if not docs:
        return None
    conteudo = docs[0].get('conteudo')
    html = conteudo[0] if isinstance(conteudo, list) else conteudo
    if not html:
        return None
    return {'source': 'resenha', 'html': html}


_INGOV_SECTIONS = ('dou1', 'dou3')


def fetch_ingov_listing(reference_date: date, timeout: int, user_agent: str) -> dict:
    """Busca a listagem pública do DOU (seções 1 e 3) para a data informada. Sempre
    retorna um dict (possivelmente com listas vazias); levanta `FetchError` em falha de
    rede/HTTP."""
    data_br = reference_date.strftime('%d-%m-%Y')
    htmls: list[str] = []
    for secao in _INGOV_SECTIONS:
        params = urllib.parse.urlencode({'data': data_br, 'secao': secao})
        raw, _status, charset = _get(f'{INGOV_LISTING_URL}?{params}', timeout, user_agent)
        htmls.append(raw.decode(charset, errors='replace'))
    return {'source': 'ingov_listing', 'htmls': htmls}


def fetch_sei_publications(reference_date: date, timeout: int, user_agent: str) -> dict:
    """Busca as publicações do SEI (boletim) para a data informada — a fonte usada pela
    antecipação da véspera (spec 009, User Story 2). Mesmo domínio já em escopo do
    Princípio II (sei.cade.gov.br), não a Resenha nem o in.gov.br.

    Validado ao vivo (2026-09-28): `SEI_PUBLICATIONS_URL` é o formulário de pesquisa
    (`frmPublicacaoPesquisa`, method="post", mesma URL como action). GET sozinho devolve
    só o formulário vazio, nunca resultados — precisa do mesmo padrão de
    `apps/monitoring/extractors.py::_resolve_process_detail` (GET dos defaults do
    formulário, depois POST com os campos de busca sobre esses defaults). Sempre retorna
    um dict; levanta `FetchError` em falha de rede/HTTP."""
    from apps.monitoring.extractors import extract_input_defaults

    get_raw, _status, get_charset = _get(SEI_PUBLICATIONS_URL, timeout, user_agent)
    defaults = extract_input_defaults(get_raw.decode(get_charset, errors='replace'))

    data_br = reference_date.strftime('%d/%m/%Y')
    payload = dict(defaults)
    payload.update({
        'rdoDataPublicacao': 'E',
        'txtDataInicio': data_br,
        'txtDataFim': data_br,
        'selOrgao[]': '0',
    })
    request = urllib.request.Request(
        SEI_PUBLICATIONS_URL,
        data=urllib.parse.urlencode(payload, doseq=True).encode('utf-8'),
        method='POST',
        headers={
            **_DEFAULT_HEADERS,
            'User-Agent': user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://sei.cade.gov.br',
            'Referer': SEI_PUBLICATIONS_URL,
        },
    )
    raw, _status, charset = _open_request(request, timeout)
    return {'source': 'sei_publications', 'html': raw.decode(charset, errors='replace')}


def _fold(text: str) -> str:
    import unicodedata
    normalized = unicodedata.normalize('NFKD', (text or '').lower())
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


CADE_HIERARCHY_MARKER = 'conselho administrativo de defesa econ'


def is_cade_item(hierarchy_text: str) -> bool:
    return CADE_HIERARCHY_MARKER in _fold(hierarchy_text)

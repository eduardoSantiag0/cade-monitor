"""
Cartão de "próxima sessão de julgamento" do dashboard (spec 010).

Escopo reduzido: só a sessão e o link da pauta — ver
specs/010-hub-proxima-sessao/spec.md, Assumptions, para o que ficou de fora e por quê.

Duas funções de leitura (`proxima_sessao`, `pauta_url`) só leem o cache — nunca
fazem HTTP, chamadas pela view. Duas de escrita (`refresh_sessoes`, `refresh_pauta`)
buscam as fontes públicas do CADE e atualizam o cache — chamadas pelo `run_worker`,
nunca pela view. Nenhuma das quatro lança exceção para o chamador: falha de rede ou
parsing vira "sem cartão", nunca erro visível.
"""
from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from urllib.parse import unquote

from django.conf import settings
from django.core.cache import cache

from apps.monitoring.clients import FetchError

logger = logging.getLogger(__name__)

CALENDARIO_SESSOES_URL = 'https://www.gov.br/cade/pt-br/assuntos/sessoes/calendario-de-sessoes'
PAUTAS_ANO_URL = 'https://www.gov.br/cade/pt-br/assuntos/sessoes/sessoes%20de%20julgamento/{ano}'

CACHE_SESSOES_TTL = 7 * 24 * 3600
CACHE_PAUTA_OK_TTL = 7 * 24 * 3600
CACHE_PAUTA_FALHA_TTL = 6 * 3600

_MESES = {
    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'março': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9,
    'outubro': 10, 'novembro': 11, 'dezembro': 12,
}


def _open_request(request: urllib.request.Request, timeout: int) -> tuple[bytes, int, str]:
    """Mesma política de retry/backoff de `apps.monitoring.clients._open_request`
    (duplicada, não importada — é uma função privada de outro app)."""
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

    raise FetchError(f'Falha ao acessar {request.full_url}: {last_error}')


def _get(url: str, timeout: int, user_agent: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
        },
    )
    raw, _status, charset = _open_request(request, timeout)
    return raw.decode(charset, errors='replace')


def _should_fetch(source: str) -> bool:
    """Cadência mínima entre tentativas à mesma fonte (mesmo espírito de
    `DouFetchState`/`_should_fetch` da feature 009, aqui como chaves de cache)."""
    key = f'hub:last_attempt:{source}'
    last = cache.get(key)
    now = datetime.now(timezone.utc)
    if last and (now - last).total_seconds() < settings.HUB_FETCH_MIN_INTERVAL_SECONDS:
        return False
    cache.set(key, now, timeout=None)
    return True


# ---------------------------------------------------------------------------
# Calendário de sessões de julgamento
# ---------------------------------------------------------------------------

def sessoes_do_html(html: str) -> list[tuple[str, str]]:
    """Extrai [(data ISO, título)] do calendário de sessões do site do CADE.

    O HTML do gov.br quebra o texto em pedaços ("05", "-", "269", "ª", "Sessão
    Ordinária"), então o parser anda linha a linha do texto sem tags, carregando
    o ano e o mês correntes, e junta as linhas soltas de cada dia até o próximo
    marcador."""
    texto = re.sub(r'<[^>]+>', '\n', html)
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    sessoes: list[tuple[str, str]] = []
    ano = mes = 0
    dia = 0
    partes: list[str] = []

    def fecha() -> None:
        nonlocal dia, partes
        if ano and mes and dia:
            titulo = re.sub(r'\s+', ' ', ' '.join(partes)).strip(' -')
            titulo = titulo.replace(' ª', 'ª')
            if re.search(r'sess[ãa]o', titulo, re.I):
                try:
                    sessoes.append((date(ano, mes, dia).isoformat(), titulo))
                except ValueError:
                    pass
        dia, partes = 0, []

    for linha in linhas:
        if re.fullmatch(r'20\d{2}', linha):
            fecha()
            ano, mes = int(linha), 0
            continue
        chave = linha.lower()
        if chave in _MESES:
            fecha()
            mes = _MESES[chave]
            continue
        inteira = re.fullmatch(r'(\d{1,2})\s*-\s*(.+)', linha)
        if inteira and mes and 1 <= int(inteira.group(1)) <= 31:
            fecha()
            dia = int(inteira.group(1))
            partes.append(inteira.group(2))
            continue
        if re.fullmatch(r'\d{1,2}', linha) and mes and 1 <= int(linha) <= 31:
            fecha()
            dia = int(linha)
            continue
        if dia:
            partes.append(linha)
    fecha()
    return sorted(set(sessoes))


def refresh_sessoes(timeout: int, user_agent: str) -> None:
    """Busca o calendário de sessões e atualiza `hub:sessoes`. Nunca lança
    exceção para o chamador (`run_worker`)."""
    if not _should_fetch('sessoes'):
        return
    try:
        html = _get(CALENDARIO_SESSOES_URL, timeout, user_agent)
        sessoes = sessoes_do_html(html)
    except FetchError as exc:
        logger.warning('[hub] Falha ao buscar o calendário de sessões: %s', exc)
        return
    if sessoes:
        cache.set('hub:sessoes', sessoes, timeout=CACHE_SESSOES_TTL)


def proxima_sessao() -> dict | None:
    """A próxima sessão de julgamento (inclusive a de hoje), lida só do cache —
    nunca faz HTTP. `None` sem cache ou sem sessão futura nele."""
    sessoes = cache.get('hub:sessoes')
    if not sessoes:
        return None
    hoje = date.today().isoformat()
    futuras = [(data, titulo) for data, titulo in sessoes if data >= hoje]
    if not futuras:
        return None
    data, titulo = min(futuras)
    return {'data': data, 'titulo': titulo}


# ---------------------------------------------------------------------------
# Pauta da sessão
# ---------------------------------------------------------------------------

def pauta_do_html(html: str, ano: int, numero: int) -> str:
    """URL do PDF da pauta na página anual: o CDN organiza por /{ano}/{nº}/ e o
    nome do arquivo traz "pauta"."""
    padrao = re.compile(
        rf'href="(https://cdn\.cade\.gov\.br/[^"]*/{ano}/{numero}/[^"]*)"', re.I,
    )
    for m in padrao.finditer(html):
        if 'pauta' in unquote(m.group(1)).lower():
            return m.group(1)
    return ''


def refresh_pauta(timeout: int, user_agent: str) -> None:
    """Busca a URL da pauta da sessão em exibição e atualiza `hub:pauta:{ano}:{numero}`.
    Sem sessão futura conhecida, não há o que buscar. Nunca lança exceção."""
    sessao = proxima_sessao()
    if not sessao:
        return
    m = re.search(r'(\d+)ª', sessao['titulo'])
    if not m:
        return
    ano, numero = int(sessao['data'][:4]), int(m.group(1))
    if not _should_fetch('pauta'):
        return
    key = f'hub:pauta:{ano}:{numero}'
    try:
        html = _get(PAUTAS_ANO_URL.format(ano=ano), timeout, user_agent)
        url = pauta_do_html(html, ano, numero)
    except FetchError as exc:
        logger.warning('[hub] Falha ao buscar a pauta da sessão %s/%s: %s', ano, numero, exc)
        return
    cache.set(key, url, timeout=CACHE_PAUTA_OK_TTL if url else CACHE_PAUTA_FALHA_TTL)


def pauta_url(sessao: dict) -> str:
    """URL da pauta da sessão informada, lida só do cache — nunca faz HTTP.
    `''` quando não está (ainda) no cache."""
    m = re.search(r'(\d+)ª', sessao.get('titulo', ''))
    if not m:
        return ''
    ano, numero = int(sessao['data'][:4]), int(m.group(1))
    return cache.get(f'hub:pauta:{ano}:{numero}') or ''

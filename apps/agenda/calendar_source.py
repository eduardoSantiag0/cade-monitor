"""
Calendário oficial de dias úteis do CADE (spec 011): busca, parsing e validação
da Portaria anual de feriados nacionais/pontos facultativos da Administração
Pública Federal (DOU), e a leitura desse calendário já persistido.

Fonte: busca por termo em `www.in.gov.br/consulta/-/buscar/dou` (mesmo portlet
`params` que `apps/dou/parsers.py` já validou ao vivo para a listagem por data —
aqui é a variante por busca textual, ainda não validada ao vivo nesta feature; ver
research.md). Já em escopo constitucional (emenda v2.2.0, feature 009).

Determinístico de ponta a ponta: nenhuma extração por IA. Portaria com formato
que o regex não reconheça reprova na validação (poucas datas) em vez de aceitar
uma lista incompleta como se fosse o calendário inteiro (FR-002).
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.monitoring.clients import FetchError

from .models import CadeCalendarEntry, CadeCalendarYear

logger = logging.getLogger(__name__)

DOU_BUSCA_URL = 'https://www.in.gov.br/consulta/-/buscar/dou'
DOU_ARTIGO_BASE = 'https://www.in.gov.br/web/dou/-/'

_PARAMS_RE = re.compile(r'id="[^"]*BuscaDouPortlet_params"[^>]*>(.*?)</script>', re.I | re.S)

_MESES = {
    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'março': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9,
    'outubro': 10, 'novembro': 11, 'dezembro': 12,
}

# Órgãos que já editaram a portaria anual (o nome mudou com reformas
# administrativas — validar por um nome fixo quebraria a busca retroativa).
_ORGAOS_COMPETENTES = (
    'ministerio da gestao e da inovacao em servicos publicos',
    'ministerio da economia',
    'ministerio do planejamento',
)
_ESCOPO_APF = ('administracao publica federal', 'direta', 'autarquica', 'fundacional')

# Inciso romano + "N de mês[, nome](parêntese)" — ex. "I - 1º de janeiro (Confraternização
# Universal)". Aceita ':'/';'/'.'/"; e " como separador antes do inciso (primeiro/último
# item da lista vêm colados no texto de abertura/fecho do artigo).
_ITEM_PORTARIA_RE = re.compile(
    r'(?:^|[;:.])\s*(?:e\s+)?[IVXL]{1,6}\s*[-–—]\s*'
    r'(\d{1,2})\s*[ºo°]?\s+de\s+([a-zçãéêó]+)'
    r'\s*(?:,\s*([^(;]+?))?\s*'
    r'\(([^)]+)\)',
    re.I,
)


def _fold(text: object) -> str:
    import unicodedata
    normalized = unicodedata.normalize('NFKD', str(text or '').lower())
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def _open_request(request: urllib.request.Request, timeout: int) -> tuple[bytes, int, str]:
    """Mesmo padrão de retry/backoff de `apps.monitoring.clients._open_request`."""
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
    request = urllib.request.Request(url, headers={
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
    })
    raw, _status, charset = _open_request(request, timeout)
    return raw.decode(charset, errors='replace')


def _params_dou(html: str) -> dict:
    match = _PARAMS_RE.search(html or '')
    if not match:
        return {}
    try:
        return json.loads(html_lib.unescape(match.group(1))) or {}
    except (ValueError, AttributeError):
        return {}


def _texto_limpo(bruto: object) -> str:
    texto = html_lib.unescape(re.sub(r'<[^>]+>', ' ', str(bruto or '')))
    return re.sub(r'\s+', ' ', texto).strip()


def busca_dou(termo: str, de: date, ate: date, timeout: int, user_agent: str) -> list[dict]:
    query = urllib.parse.urlencode({
        'q': f'"{termo}"', 's': 'do1', 'exactDate': 'personalizado',
        'publishFrom': de.strftime('%d-%m-%Y'), 'publishTo': ate.strftime('%d-%m-%Y'),
    })
    html = _get(f'{DOU_BUSCA_URL}?{query}', timeout, user_agent)
    return _params_dou(html).get('jsonArray') or []


_TEXTO_DOU_RE = re.compile(r'class="texto-dou"[^>]*>(.*?)</div>\s*</div>', re.S)


def texto_integral_dou(item: dict, timeout: int, user_agent: str) -> str:
    """Texto completo do artigo — o `content` da listagem de busca vem truncado
    (~300 caracteres). Validado ao vivo (2026-09-28, ver research.md): a página
    de artigo individual não embute o mesmo JSON `params` da listagem de busca —
    o corpo real está em HTML puro, `<div class="texto-dou">` com um
    `<p class="dou-paragraph">` por parágrafo."""
    slug = str(item.get('urlTitle') or '').strip()
    parcial = _texto_limpo(item.get('content'))
    if not slug:
        return parcial
    try:
        html = _get(f'{DOU_ARTIGO_BASE}{slug}', timeout, user_agent)
    except FetchError:
        return parcial
    melhor = parcial
    for artigo in _params_dou(html).get('jsonArray') or []:
        completo = _texto_limpo(artigo.get('content') or artigo.get('texto'))
        if len(completo) > len(melhor):
            melhor = completo
    match = _TEXTO_DOU_RE.search(html)
    if match:
        completo = _texto_limpo(match.group(1))
        if len(completo) > len(melhor):
            melhor = completo
    return melhor


def _extrai_entradas_portaria(texto: str, ano: int) -> list[tuple[date, str]]:
    """[(data, nome)] a partir do art. 1º da portaria anual. Todo inciso encontrado
    conta como dia não útil — sem distinguir feriado/ponto facultativo parcial
    (spec.md não exige essa granularidade; FR-001 só precisa de "dia útil sim/não")."""
    vistos: dict[date, str] = {}
    for match in _ITEM_PORTARIA_RE.finditer(texto or ''):
        dia_txt, mes_txt, nome_txt, parentese = match.groups()
        mes = _MESES.get(_fold(mes_txt))
        if not mes:
            continue
        try:
            dia = date(ano, mes, int(dia_txt))
        except ValueError:
            continue
        if dia in vistos:
            continue
        nome = re.sub(r'\s+', ' ', (nome_txt or parentese or '').strip(' ,;')) or 'Ponto não útil'
        vistos[dia] = nome
    return sorted(vistos.items())


def _numero_do_ato(titulo: str) -> str:
    match = re.search(r'n[º°ºo.]?\s*([\d.]+)', titulo or '', re.I)
    return match.group(1).strip(' .') if match else ''


def _valida_portaria(item: dict, texto: str, ano: int, entradas: list[tuple[date, str]]) -> tuple[bool, str]:
    """FR-002: é Portaria, do órgão competente, Seção 1, não revogada, referencia
    o ano-alvo, tem um número mínimo de datas, nenhuma fora do ano."""
    titulo = _texto_limpo(item.get('title'))
    hierarquia = _fold(_texto_limpo(item.get('hierarchyStr')))
    dobrado = _fold(texto)
    if not re.search(r'\bportaria\b', _fold(titulo)):
        return False, 'O ato encontrado não é uma portaria.'
    if not any(orgao in hierarquia for orgao in _ORGAOS_COMPETENTES):
        return False, f'Órgão emissor fora da lista de competentes: {hierarquia[:80]}'
    if str(item.get('pubName') or '').upper() not in ('DO1', 'DO1E'):
        return False, 'Publicação fora da Seção 1 do DOU.'
    for termo in _ESCOPO_APF:
        if termo not in dobrado:
            return False, f'O ato não declara o escopo da APF ("{termo}" ausente).'
    if f'ano de {ano}' not in dobrado and f'de {ano}' not in dobrado:
        return False, f'O ato não se refere ao ano de {ano}.'
    if 'revogad' in dobrado[:400]:
        return False, 'O ato aparece como revogado.'
    if len(entradas) < 8:
        return False, f'Só {len(entradas)} data(s) extraída(s); esperado o calendário inteiro.'
    fora = [dia for dia, _nome in entradas if dia.year != ano]
    if fora:
        return False, f'Datas fora do ano-alvo: {fora[:3]}'
    return True, ''


def _busca_portaria_anual(year: int, timeout: int, user_agent: str) -> dict:
    """Localiza a portaria anual para `year`. Nunca levanta — devolve
    {'ok', 'entradas', 'ato', 'titulo', 'url', 'erro'}."""
    resultado: dict = {'ok': False, 'entradas': [], 'ato': '', 'titulo': '', 'url': '', 'erro': ''}
    try:
        itens = busca_dou(
            'dias de feriados nacionais', date(year - 1, 10, 1), date(year, 3, 31), timeout, user_agent,
        )
    except FetchError as exc:
        resultado['erro'] = str(exc)
        return resultado
    reprovas: list[str] = []
    for item in itens:
        titulo = _texto_limpo(item.get('title'))
        if not re.search(r'\bportaria\b', _fold(titulo)):
            continue
        try:
            texto = texto_integral_dou(item, timeout, user_agent)
        except FetchError as exc:
            reprovas.append(f'{titulo[:50]}: {exc}')
            continue
        entradas = _extrai_entradas_portaria(texto, year)
        ok, motivo = _valida_portaria(item, texto, year, entradas)
        if not ok:
            reprovas.append(f'{titulo[:50]}: {motivo}')
            continue
        url_title = item.get('urlTitle')
        resultado.update({
            'ok': True, 'entradas': entradas, 'ato': _numero_do_ato(titulo), 'titulo': titulo,
            'url': f'{DOU_ARTIGO_BASE}{url_title}' if url_title else '',
        })
        return resultado
    resultado['erro'] = (
        'Portaria anual não localizada. '
        + ('Reprovas: ' + '; '.join(reprovas[:3]) if reprovas else 'Sem candidatos.')
    )
    return resultado


def sync_calendar_year(year: int, timeout: int, user_agent: str) -> None:
    """Busca/valida/persiste o calendário oficial de `year` (FR-001/002/003).
    Gate de cadência via `CadeCalendarYear.next_check_at`. Nunca lança exceção —
    falha vira log + reagendamento."""
    now = timezone.now()
    record, _created = CadeCalendarYear.objects.get_or_create(year=year)
    if record.next_check_at and now < record.next_check_at:
        return

    resultado = _busca_portaria_anual(year, timeout, user_agent)
    record.last_checked_at = now
    if resultado['ok']:
        record.status = CadeCalendarYear.Status.CONFIRMED
        record.official_act = resultado['ato']
        record.official_source_url = resultado['url']
        record.next_check_at = now + timedelta(
            seconds=settings.AGENDA_CALENDAR_SYNC_CONFIRMED_INTERVAL_SECONDS,
        )
        record.save()
        CadeCalendarEntry.objects.filter(calendar_year=record).delete()
        CadeCalendarEntry.objects.bulk_create([
            CadeCalendarEntry(calendar_year=record, date=dia, name=nome)
            for dia, nome in resultado['entradas']
        ])
        logger.info('[agenda] Calendário %s confirmado: %s (%d dias não úteis).',
                     year, resultado['ato'], len(resultado['entradas']))
    else:
        record.next_check_at = now + timedelta(
            seconds=settings.AGENDA_CALENDAR_SYNC_INTENSIVE_INTERVAL_SECONDS,
        )
        record.save()
        logger.info('[agenda] Calendário %s ainda não confirmado: %s', year, resultado['erro'])


def is_business_day(day: date) -> bool:
    """`True` quando não é fim de semana nem um dia não útil confirmado do ano
    de `day`. Ano sem calendário confirmado: só considera fins de semana — quem
    decide o que fazer com essa incerteza é o chamador (`deadlines.py`, FR-011)."""
    if day.weekday() >= 5:
        return False
    return not CadeCalendarEntry.objects.filter(
        calendar_year__year=day.year, calendar_year__status=CadeCalendarYear.Status.CONFIRMED, date=day,
    ).exists()


def year_is_confirmed(year: int) -> bool:
    return CadeCalendarYear.objects.filter(year=year, status=CadeCalendarYear.Status.CONFIRMED).exists()

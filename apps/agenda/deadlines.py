"""
Classificação de processo, identificação de documentos e fórmula/linha do tempo de
prazos de um Ato de Concentração Sumário (spec 011). Módulo puramente funcional —
sem acesso ao banco, exceto via `calendar_source.is_business_day`/`year_is_confirmed`.

Fórmula de prazo (FR-004) e formato de classificação — ver research.md
para o racional e para o que ficar "a confirmar na implementação".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from apps.monitoring.extractors import extract_protocol_records

from . import calendar_source as cs


class CalendarNotConfirmedError(Exception):
    """O ano de calendário necessário para este cálculo ainda não está confirmado
    (FR-011) — o chamador trata como prazo pendente, nunca como erro fatal."""


def fold(text: object) -> str:
    normalized = unicodedata.normalize('NFKD', str(text or '').lower())
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def calcula_prazo_cade(data_evento: date, dias: int) -> date:
    """FR-004: início = primeiro dia útil do CADE estritamente após `data_evento`;
    vencimento preliminar = início + (dias-1) corridos; vencimento final = preliminar,
    ou o próximo dia útil se cair em dia não útil.

    Só os dois extremos (início e vencimento) são ajustados para dia útil — os dias
    do meio contam corridos, porque é assim que o CADE conta (não é "N dias úteis").

    Cada candidato a dia útil só é aceito com o calendário do SEU ano confirmado —
    nunca assume "sem feriado" para um ano ainda não confirmado (FR-011): a falta de
    confirmação vira `CalendarNotConfirmedError`, nunca uma data adivinhada.
    """
    def _proximo_dia_util(candidato: date) -> date:
        while True:
            if not cs.year_is_confirmed(candidato.year):
                raise CalendarNotConfirmedError(f'Calendário de {candidato.year} não confirmado.')
            if cs.is_business_day(candidato):
                return candidato
            candidato += timedelta(days=1)

    inicio = _proximo_dia_util(data_evento + timedelta(days=1))
    preliminar = inicio + timedelta(days=dias - 1)
    return _proximo_dia_util(preliminar)


# ---------------------------------------------------------------------------
# Classificação do processo (FR-005)
# ---------------------------------------------------------------------------

_TIPO_PROCESSO_RE = re.compile(r'tipo\s+d[eo]\s+processo\s*:\s*([^\n]{0,200})')
_EXCLUDED_CLASSIFICATIONS = ('ordinari', 'apuracao', 'consulta', 'recurso')


def classifica_processo(last_text: str) -> str | None:
    """`'ac_sumario'` quando a classificação bate com Ato de Concentração Sumário;
    `None` para qualquer outra coisa, inclusive as classificações da lista de
    exclusão de FR-005 (ordinário, apuração, consulta, recurso)."""
    folded = fold(last_text)
    match = _TIPO_PROCESSO_RE.search(folded)
    label = match.group(1) if match else folded
    if any(term in label for term in _EXCLUDED_CLASSIFICATIONS):
        return None
    if 'ato de concentracao' in label and 'sumari' in label:
        return 'ac_sumario'
    return None


# ---------------------------------------------------------------------------
# Identificação de documentos (FR-006)
# ---------------------------------------------------------------------------

@dataclass
class DocumentMatch:
    record: dict
    confidence: float


def _br_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, '%d/%m/%Y').date()
    except (ValueError, TypeError):
        return None


def _first_matching(records: list[dict], predicate, confidence: float) -> DocumentMatch | None:
    matches = [r for r in records if predicate(fold(r.get('doc_type', '')))]
    if not matches:
        return None
    earliest = min(matches, key=lambda r: r.get('sort_key', ''))
    return DocumentMatch(record=earliest, confidence=confidence)


def match_notificacao(records: list[dict]) -> DocumentMatch | None:
    """Documento de notificação (protocolo de abertura) — ignora
    recibos/emendas/complementações/respostas (Edge Case da spec)."""
    def is_notificacao(doc_type: str) -> bool:
        if 'notifica' not in doc_type:
            return False
        return not any(term in doc_type for term in ('complementa', 'emenda', 'resposta', 'recibo'))
    return _first_matching(records, is_notificacao, confidence=0.9)


def match_edital(records: list[dict]) -> DocumentMatch | None:
    return _first_matching(records, lambda t: 'edital' in t, confidence=0.9)


def match_publicacao_edital(records: list[dict]) -> DocumentMatch | None:
    """A publicação do edital/notificação no DOU — usa a data de registro no SEI
    como aproximação da data de publicação real (sem integração direta com o
    digest do DOU nesta versão — plan.md, Assumptions). A mais antiga: é a que
    acompanha o edital, não uma publicação posterior (ex.: do despacho)."""
    return _first_matching(records, lambda t: 'publica' in t, confidence=0.7)


def match_publicacao_aprovacao(records: list[dict], aprovacao_sort_key: str) -> DocumentMatch | None:
    """A publicação do despacho de aprovação no DOU — a primeira publicação
    registrada no SEI a partir da data do próprio despacho (nunca antes dele)."""
    posteriores = [r for r in records if r.get('sort_key', '') >= aprovacao_sort_key]
    return _first_matching(posteriores, lambda t: 'publica' in t, confidence=0.7)


def match_aprovacao(records: list[dict]) -> DocumentMatch | None:
    """Despacho de aprovação da SG — distinto de despacho ORDINATÓRIO e de
    despacho decisório de ACESSO RESTRITO (nunca confundidos, spec.md)."""
    def is_aprovacao(doc_type: str) -> bool:
        if 'despacho' not in doc_type:
            return False
        if 'ordinatorio' in doc_type or 'acesso restrito' in doc_type:
            return False
        return True

    def is_aprovacao_sg_explicita(doc_type: str) -> bool:
        return is_aprovacao(doc_type) and ('aprov' in doc_type or ' sg' in f' {doc_type}')

    exact = _first_matching(records, is_aprovacao_sg_explicita, confidence=0.85)
    if exact:
        return exact
    return _first_matching(records, is_aprovacao, confidence=0.5)


def match_certidao(records: list[dict]) -> DocumentMatch | None:
    """Certidão de trânsito em julgado — NUNCA confundida com 'certidão de
    julgamento' (exige o termo 'trânsito', não só 'certidão' + 'julgado')."""
    def is_certidao(doc_type: str) -> bool:
        return 'certidao' in doc_type and 'transito' in doc_type
    return _first_matching(records, is_certidao, confidence=0.9)


# ---------------------------------------------------------------------------
# Linha do tempo (FR-007 a FR-011)
# ---------------------------------------------------------------------------

def _prazo_item(tipo: str, vencimento: date | None, estimado: bool, confidence: float,
                 pendente: bool = False) -> dict:
    return {
        'tipo': tipo, 'vencimento': vencimento, 'estimado': estimado,
        'confidence': confidence, 'pendente': pendente,
    }


def monta_linha_do_tempo(process) -> list[dict]:
    """Lista de prazos (FR-007 a FR-010) para `process`, ou lista vazia quando não
    é um AC sumário (FR-005) ou não há nenhum documento identificável ainda.
    Nunca lança exceção — ano de calendário não confirmado vira item pendente
    (FR-011), nunca uma data adivinhada."""
    if classifica_processo(process.last_text) != 'ac_sumario':
        return []

    records = extract_protocol_records(process.last_text or '')
    notificacao = match_notificacao(records)
    edital = match_edital(records)
    publicacao = match_publicacao_edital(records)
    aprovacao = match_aprovacao(records)
    certidao = match_certidao(records)

    itens: list[dict] = []

    if notificacao and not aprovacao:
        data_evento = _br_date(notificacao.record['registry_date'])
        if data_evento:
            try:
                vencimento = calcula_prazo_cade(data_evento, 30)
                itens.append(_prazo_item('analise_sg', vencimento, False, notificacao.confidence))
            except CalendarNotConfirmedError:
                itens.append(_prazo_item('analise_sg', None, False, notificacao.confidence, pendente=True))

    if edital or publicacao:
        base = publicacao or edital
        data_evento = _br_date(base.record['registry_date'])
        if data_evento:
            try:
                vencimento = calcula_prazo_cade(data_evento, 15)
                itens.append(_prazo_item('terceiro_interessado', vencimento, False, base.confidence))
            except CalendarNotConfirmedError:
                itens.append(_prazo_item('terceiro_interessado', None, False, base.confidence, pendente=True))

    recurso_vencimento: date | None = None
    if aprovacao:
        publicacao_aprovacao = match_publicacao_aprovacao(records, aprovacao.record['sort_key'])
        base_recurso = publicacao_aprovacao or aprovacao
        data_evento = _br_date(base_recurso.record['registry_date'])
        if data_evento:
            try:
                recurso_vencimento = calcula_prazo_cade(data_evento, 15)
                itens.append(_prazo_item('recurso_avocacao', recurso_vencimento, False, aprovacao.confidence))
            except CalendarNotConfirmedError:
                itens.append(_prazo_item('recurso_avocacao', None, False, aprovacao.confidence, pendente=True))

    if certidao:
        data_evento = _br_date(certidao.record['registry_date'])
        if data_evento:
            itens.append(_prazo_item('certidao_final', data_evento, False, certidao.confidence))
    elif recurso_vencimento:
        try:
            prevista = recurso_vencimento + timedelta(days=1)
            while not cs.is_business_day(prevista):
                prevista += timedelta(days=1)
            itens.append(_prazo_item('certidao_final', prevista, True, aprovacao.confidence if aprovacao else 0.5))
        except Exception:  # noqa: BLE001 — previsão é um bônus, nunca derruba a linha do tempo
            pass

    return itens

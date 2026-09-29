"""
Orquestração do digest DOU (spec 009): busca, formatação e envio. Chamado a cada tick
de `run_worker._run_cycle` — cada `run_*_window` decide internamente se há algo a
fazer neste tick (janela diária + cadência mínima entre tentativas) e nunca lança
exceção para o chamador (Constitution Check em plan.md; contracts/dou-services.md).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from .models import DouFetchState

logger = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(':')
    return time(int(hour), int(minute))


def _should_fetch(source: str, now: datetime) -> bool:
    """Aplica a cadência mínima entre tentativas à mesma fonte (emenda v2.2.0 do
    Princípio II). Sempre grava a tentativa atual quando permite buscar — o chamador
    não precisa (e não deve) atualizar `DouFetchState` por conta própria."""
    state, _created = DouFetchState.objects.get_or_create(source=source)
    min_interval = timedelta(seconds=settings.DOU_FETCH_MIN_INTERVAL_SECONDS)
    if state.last_attempt_at and now - state.last_attempt_at < min_interval:
        return False
    state.last_attempt_at = now
    state.save(update_fields=['last_attempt_at'])
    return True


def _mark_fetch_success(source: str, now: datetime) -> None:
    DouFetchState.objects.filter(source=source).update(last_success_at=now)


def _within_window(now: datetime, start: str, end: str) -> bool:
    """`start`/`end` são horários `HH:MM` (sem segundos) — a comparação trunca o
    segundo/microssegundo atual antes de comparar, para o minuto de `end` inteiro
    contar como dentro da janela (sem isso, `23:59:01`-`23:59:59` cairiam fora de
    uma janela configurada para terminar às `23:59`)."""
    local = timezone.localtime(now) if timezone.is_aware(now) else now
    current_minute = local.time().replace(second=0, microsecond=0)
    return _parse_hhmm(start) <= current_minute <= _parse_hhmm(end)


def _local_date(now: datetime):
    local = timezone.localtime(now) if timezone.is_aware(now) else now
    return local.date()


def run_digest_window(now: datetime) -> dict:
    """User Story 1 (P1): busca as publicações do CADE do dia (Resenha, com fallback
    para a listagem in.gov.br) e envia o digest a cada assinante ativo. Nunca lança
    exceção para o chamador (contracts/dou-services.md)."""
    from apps.monitoring.clients import FetchError
    from apps.notifications.channels.email import send_email_notification

    from . import selectors
    from .clients import fetch_ingov_listing, fetch_resenha
    from .models import DouSendLog
    from .parsers import parse_ingov_listing, parse_resenha_html
    from .render import digest_subject, render_digest_html

    if not _within_window(now, settings.DOU_DIGEST_WINDOW_START, settings.DOU_DIGEST_WINDOW_END):
        return {'skipped': True, 'reason': 'outside_window', 'sent': 0, 'failed': 0}

    reference_date = _local_date(now)
    dou_data: dict | None = None

    if _should_fetch(DouFetchState.Source.RESENHA, now):
        try:
            resenha = fetch_resenha(reference_date, settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
        except FetchError as exc:
            logger.warning('[dou] Falha ao buscar a Resenha: %s', exc)
        else:
            if resenha:
                dou_data = parse_resenha_html(resenha['html'])
                _mark_fetch_success(DouFetchState.Source.RESENHA, now)

    if dou_data is None and _should_fetch(DouFetchState.Source.INGOV_LISTING, now):
        try:
            listing = fetch_ingov_listing(reference_date, settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
        except FetchError as exc:
            logger.warning('[dou] Falha ao buscar a listagem in.gov.br: %s', exc)
        else:
            dou_data = parse_ingov_listing(listing['htmls'])
            _mark_fetch_success(DouFetchState.Source.INGOV_LISTING, now)

    if dou_data is None:
        return {'skipped': True, 'reason': 'no_source_available', 'sent': 0, 'failed': 0}

    sent = failed = 0
    for subscription in selectors.active_digest_subscriptions():
        if selectors.already_sent(subscription, DouSendLog.Kind.DIGEST, reference_date):
            continue
        if not subscription.subscriber.is_reachable():
            continue
        terms = selectors.monitored_terms(subscription)
        html = render_digest_html(dou_data, terms, reference_date, now)
        status, error = send_email_notification(
            subscription.subscriber.email, digest_subject(reference_date), html, html=True,
        )
        DouSendLog.objects.create(
            subscription=subscription, kind=DouSendLog.Kind.DIGEST, reference_date=reference_date,
            status=DouSendLog.Status.SENT if status == 'sent' else DouSendLog.Status.FAILED,
            error=error or '',
        )
        if status == 'sent':
            sent += 1
        else:
            failed += 1
            logger.warning('[dou] Falha ao enviar digest para %s: %s', subscription.subscriber.email, error)

    return {'skipped': False, 'sent': sent, 'failed': failed}


def run_anticipation_window(now: datetime) -> dict:
    """User Story 2 (P2): para assinantes com antecipação habilitada, no horário
    configurado de cada um, antecipa do boletim do SEI os andamentos que devem sair no
    DOU do dia seguinte; reenvia só os itens novos (complemento) até o horário-limite
    da noite. Nunca lança exceção para o chamador.

    ponytail: "dia seguinte" é o próximo dia corrido, não o próximo dia útil do
    calendário de expediente do CADE (essa calculadora é a feature separada de
    Agenda/Prazos, ainda não portada) — upgrade quando `calendario.py` existir.
    """
    from apps.monitoring.clients import FetchError
    from apps.notifications.channels.email import send_email_notification

    from . import selectors
    from .clients import fetch_sei_publications
    from .models import DouAnticipation, DouSendLog
    from .parsers import parse_sei_publications
    from .render import pubdou_subject, render_pubdou_html

    local_now = timezone.localtime(now) if timezone.is_aware(now) else now
    if local_now.time() > _parse_hhmm(settings.DOU_ANTICIPATION_CUTOFF):
        return {'skipped': True, 'reason': 'after_cutoff', 'sent': 0, 'failed': 0}

    subscriptions = selectors.active_anticipation_subscriptions()
    if not subscriptions:
        return {'skipped': True, 'reason': 'no_subscribers', 'sent': 0, 'failed': 0}

    bulletin_date = _local_date(now)
    dou_date = bulletin_date + timedelta(days=1)

    items: list[dict] | None = None
    if _should_fetch(DouFetchState.Source.SEI_PUBLICATIONS, now):
        try:
            sei = fetch_sei_publications(bulletin_date, settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
        except FetchError as exc:
            logger.warning('[dou] Falha ao buscar publicações do SEI: %s', exc)
        else:
            items = parse_sei_publications(sei['html'])
            _mark_fetch_success(DouFetchState.Source.SEI_PUBLICATIONS, now)

    if items is None:
        return {'skipped': True, 'reason': 'no_source_available', 'sent': 0, 'failed': 0}

    sent = failed = 0
    for subscription in subscriptions:
        if local_now.time() < subscription.nextday_time:
            continue
        if not subscription.subscriber.is_reachable():
            continue

        anticipation, created = DouAnticipation.objects.get_or_create(
            subscription=subscription, reference_date=dou_date, defaults={'items': items},
        )
        if created:
            kind, payload = DouSendLog.Kind.PUBDOU_ANT, items
        else:
            known_texts = {i.get('text') for i in anticipation.items}
            new_items = [i for i in items if i.get('text') not in known_texts]
            if not new_items:
                continue
            if selectors.already_sent(subscription, DouSendLog.Kind.PUBDOU_COMPL, dou_date):
                anticipation.items = items
                anticipation.save(update_fields=['items'])
                continue
            kind, payload = DouSendLog.Kind.PUBDOU_COMPL, new_items
            anticipation.items = items
            anticipation.save(update_fields=['items'])

        terms = selectors.monitored_terms(subscription)
        html = render_pubdou_html(payload, terms, dou_date, now)
        status, error = send_email_notification(
            subscription.subscriber.email, pubdou_subject(dou_date), html, html=True,
        )
        DouSendLog.objects.create(
            subscription=subscription, kind=kind, reference_date=dou_date,
            status=DouSendLog.Status.SENT if status == 'sent' else DouSendLog.Status.FAILED,
            error=error or '',
        )
        if status == 'sent':
            sent += 1
        else:
            failed += 1
            logger.warning('[dou] Falha ao enviar antecipação para %s: %s', subscription.subscriber.email, error)

    return {'skipped': False, 'sent': sent, 'failed': failed}


_PROC_NUMBER_RE = re.compile(r'\d{5}\.\d{6}/\d{4}-\d{2}')


def _process_numbers(item: dict) -> set[str]:
    return set(_PROC_NUMBER_RE.findall(f"{item.get('titulo', '')} {item.get('text', '')}"))


def run_confirmation_window(now: datetime) -> dict:
    """User Story 3 (P3): para assinantes com uma antecipação de hoje, compara com o
    DOU real do dia e confirma o que foi publicado (ou aponta o que ficou de fora).
    Reaproveita as mesmas fontes/`DouFetchState` de `run_digest_window` — a cadência
    mínima entre tentativas é por FONTE externa, não por feature interna que a chama
    (Princípio II, emenda v2.2.0). Nunca lança exceção para o chamador."""
    from apps.monitoring.clients import FetchError
    from apps.notifications.channels.email import send_email_notification

    from . import selectors
    from .clients import fetch_ingov_listing, fetch_resenha
    from .models import DouAnticipation, DouSendLog
    from .parsers import parse_ingov_listing, parse_resenha_html
    from .render import item_lead_reference, render_confirmation_html

    if not _within_window(now, settings.DOU_CONFIRMATION_WINDOW_START, settings.DOU_CONFIRMATION_WINDOW_END):
        return {'skipped': True, 'reason': 'outside_window', 'sent': 0, 'failed': 0}

    reference_date = _local_date(now)
    anticipations = [
        a for a in DouAnticipation.objects.select_related('subscription__subscriber')
        .filter(reference_date=reference_date, subscription__nextday_enabled=True)
        if a.items
    ]
    if not anticipations:
        return {'skipped': True, 'reason': 'no_anticipations', 'sent': 0, 'failed': 0}

    dou_data: dict | None = None
    if _should_fetch(DouFetchState.Source.RESENHA, now):
        try:
            resenha = fetch_resenha(reference_date, settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
        except FetchError as exc:
            logger.warning('[dou] Falha ao buscar a Resenha (confirmação): %s', exc)
        else:
            if resenha:
                dou_data = parse_resenha_html(resenha['html'])
                _mark_fetch_success(DouFetchState.Source.RESENHA, now)

    if dou_data is None and _should_fetch(DouFetchState.Source.INGOV_LISTING, now):
        try:
            listing = fetch_ingov_listing(reference_date, settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
        except FetchError as exc:
            logger.warning('[dou] Falha ao buscar a listagem in.gov.br (confirmação): %s', exc)
        else:
            dou_data = parse_ingov_listing(listing['htmls'])
            _mark_fetch_success(DouFetchState.Source.INGOV_LISTING, now)

    if dou_data is None:
        return {'skipped': True, 'reason': 'no_source_available', 'sent': 0, 'failed': 0}

    published = list(dou_data.get('editais', [])) + list(dou_data.get('despachos', []))
    nothing_published = not published
    published_by_number: dict[str, dict] = {}
    for item in published:
        for number in _process_numbers(item):
            published_by_number.setdefault(number, item)

    sent = failed = 0
    for anticipation in anticipations:
        subscription = anticipation.subscription
        if selectors.already_sent(subscription, DouSendLog.Kind.PUBDOU_CONF, reference_date):
            continue
        if not subscription.subscriber.is_reachable():
            continue

        confirmed: list[dict] = []
        missing: list[str] = []
        for anticipated_item in anticipation.items:
            matched = next(
                (published_by_number[n] for n in _process_numbers(anticipated_item) if n in published_by_number),
                None,
            )
            if matched:
                confirmed.append(matched)
            else:
                missing.append(item_lead_reference(anticipated_item))

        terms = selectors.monitored_terms(subscription)
        single = len(anticipation.items) == 1
        html = render_confirmation_html(confirmed, missing, terms, nothing_published, single)
        status, error = send_email_notification(
            subscription.subscriber.email, f'Publicação DOU | {reference_date.day}.{reference_date.month}.{reference_date.year}',
            html, html=True,
        )
        DouSendLog.objects.create(
            subscription=subscription, kind=DouSendLog.Kind.PUBDOU_CONF, reference_date=reference_date,
            status=DouSendLog.Status.SENT if status == 'sent' else DouSendLog.Status.FAILED,
            error=error or '',
        )
        if status == 'sent':
            sent += 1
        else:
            failed += 1
            logger.warning('[dou] Falha ao enviar confirmação para %s: %s', subscription.subscriber.email, error)

    return {'skipped': False, 'sent': sent, 'failed': failed}

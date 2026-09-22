"""
Execução das ações do bot que dependem do SEI (chamado pelo run_worker).

  - initial_watch: primeira leitura de um processo novo (baseline, sem alerta).
  - check: verificação sob demanda (/check).
  - latest: última atualização com o documento mais recente (/last_update e
    automaticamente após o /watch).

Ações do mesmo processo são agrupadas: no máximo UMA consulta ao SEI por
processo por tick, e todos os chats que pediram recebem a resposta.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlparse

import sentry_sdk
from django.conf import settings
from django.utils import timezone

from apps.monitoring.clients import (
    FetchError,
    _looks_like_compressed,
    download_document,
    extract_document_links,
    get_snapshot,
    lookup_process_url,
)
from apps.monitoring.extractors import latest_protocol_record
from apps.monitoring.models import DetectedDocument
from apps.monitoring.services import run_check
from apps.processes.models import MonitoredProcess, ProcessOrigin, ProcessStatus

from . import client, messages, selectors
from .models import BotAction, BotActionKind, BotActionStatus
from .services import recalculate_process_status, reply

logger = logging.getLogger(__name__)

# Tentativas rápidas (espaçadas pelo cooldown do /check) antes de cair para a
# cadência normal de monitoramento. A ação nunca expira sozinha: termina com
# sucesso, "não encontrado" ou /unwatch.
FAST_RETRY_ATTEMPTS = 3


def process_pending_bot_actions() -> int:
    """Processa ações vencidas. Retorna quantas ações foram tratadas."""
    pending = (
        BotAction.objects
        .filter(status=BotActionStatus.PENDING, next_attempt_at__lte=timezone.now())
        .select_related('chat', 'process')
        .order_by('requested_at')
    )
    by_process: dict[int, list[BotAction]] = defaultdict(list)
    for action in pending:
        by_process[action.process_id].append(action)

    for actions in by_process.values():
        try:
            _run_for_process(actions)
        except Exception as exc:
            logger.error('[telegram] Erro ao executar ações do processo #%s: %s',
                         actions[0].process_id, exc, exc_info=True)
            sentry_sdk.capture_exception(exc)
    return sum(len(a) for a in by_process.values())


def _run_for_process(actions: list[BotAction]) -> None:
    process = actions[0].process
    process.refresh_from_db()

    latest = [a for a in actions if a.kind == BotActionKind.LATEST]
    if latest:
        _send_latest_update(process, latest)

    initial = [a for a in actions if a.kind == BotActionKind.INITIAL_WATCH]
    checks = [a for a in actions if a.kind == BotActionKind.CHECK]

    # Baseline já existe (a rotina normal chegou antes): responde sem consultar.
    if process.has_baseline:
        _start_and_deliver_latest(process, initial)
        initial = []

    # /check de processo verificado dentro do cooldown (por outra via): estado salvo.
    if checks and _recently_checked(process):
        for action in checks:
            _finish(action, messages.check_no_change(process.label, selectors.latest_records(process)))
        checks = []

    if not initial and not checks:
        return

    if not process.has_baseline and not process.resolved_url and not _is_url(process.source):
        try:
            url = lookup_process_url(
                process.source,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
                user_agent=settings.USER_AGENT,
            )
        except FetchError as exc:
            logger.warning('[telegram] Lookup falhou para #%d: %s', process.pk, exc)
            _handle_fetch_failure(process, initial, checks)
            return
        if url is None:
            _handle_not_found(process, initial + checks)
            return
        process.resolved_url = url
        process.save(update_fields=['resolved_url', 'updated_at'])

    result = run_check(process)
    process.refresh_from_db()
    if not result.get('ok'):
        _handle_fetch_failure(process, initial, checks)
        return

    _start_and_deliver_latest(process, initial)
    for action in checks:
        text = (
            messages.check_changed(process.label)
            if result.get('changed')
            else messages.check_no_change(process.label, selectors.latest_records(process))
        )
        _finish(action, text)


def _send_latest_update(process: MonitoredProcess, actions: list[BotAction]) -> None:
    """/last_update: entrega texto + arquivo e conclui as ações."""
    text = _deliver_latest(process, [a.chat for a in actions])
    for action in actions:
        _finish(action, text, send=False)


def _start_and_deliver_latest(process: MonitoredProcess, actions: list[BotAction]) -> None:
    """/watch concluído: confirma o monitoramento e já envia a última atualização."""
    if not actions:
        return
    for action in actions:
        _finish(action, _started_text(process))
    _deliver_latest(process, [a.chat for a in actions])


def _deliver_latest(process: MonitoredProcess, chats: list) -> str:
    """Monta a última atualização UMA vez e envia texto + arquivo a cada chat."""
    text, attachment = _build_latest_update(process)
    for chat in chats:
        if not chat.is_reachable:
            continue
        reply(chat, text)
        if attachment:
            result = client.send_document_file(
                chat.chat_id,
                attachment['content'],
                str(attachment.get('filename') or 'documento'),
                str(attachment.get('content_type') or 'application/octet-stream'),
            )
            if not result.ok and result.is_blocked:
                from .services import mark_chat_unreachable
                mark_chat_unreachable(chat.chat_id)
    return text


def _build_latest_update(process: MonitoredProcess) -> tuple[str, dict | None]:
    """
    Texto da última atualização + arquivo do protocolo mais recente (se der).
    Usa o link já conhecido (DetectedDocument); só consulta a página do processo
    quando o link do documento ainda não foi visto pelo monitor.
    """
    record = latest_protocol_record(process.last_text)
    doc_url = ''
    note = ''
    attachment = None

    if record and record.get('document'):
        doc_url = (
            DetectedDocument.objects
            .filter(change__process=process, document_number=record['document'])
            .exclude(url='')
            .order_by('-created_at')
            .values_list('url', flat=True)
            .first()
        ) or ''
        if not doc_url:
            try:
                snapshot = get_snapshot(
                    process.effective_url,
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                    user_agent=settings.USER_AGENT,
                )
                doc_url = extract_document_links(snapshot.html, snapshot.url).get(record['document'], '')
            except FetchError as exc:
                logger.warning('[telegram] /last_update: página de #%d indisponível: %s', process.pk, exc)

    if doc_url:
        if _looks_like_compressed(record, doc_url):
            note = 'Arquivo compactado: disponível só pelo link acima.'
        else:
            try:
                attachment = download_document(
                    url=doc_url,
                    record={'document': record['document'], 'doc_type': record.get('doc_type', '')},
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                    user_agent=settings.USER_AGENT,
                    max_bytes=settings.TELEGRAM_ATTACHMENT_MAX_BYTES,
                )
                note = 'Documento em anexo logo abaixo.'
            except FetchError as exc:
                note = f'Não consegui baixar o documento agora ({exc}). Use o link acima.'
    elif record:
        note = 'Não encontrei o link público deste documento no SEI.'

    text = messages.latest_update(
        label=process.label,
        process_url=process.effective_url,
        record=record,
        doc_url=doc_url,
        change=selectors.last_change(process),
        attachment_note=note,
    )
    return text, attachment


def _started_text(process: MonitoredProcess) -> str:
    text = messages.watch_started(process.label)
    if process.status in (ProcessStatus.PAUSED, ProcessStatus.ARCHIVED) and process.origin != ProcessOrigin.TELEGRAM:
        text += messages.admin_suspended_note()
    return text


def _recently_checked(process: MonitoredProcess) -> bool:
    if not process.last_checked_at:
        return False
    return timezone.now() - process.last_checked_at < timedelta(seconds=settings.TELEGRAM_CHECK_COOLDOWN_SECONDS)


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def _handle_fetch_failure(process: MonitoredProcess, initial: list[BotAction], checks: list[BotAction]) -> None:
    for action in checks:
        _finish(action, messages.check_failed(process.label), status=BotActionStatus.FAILED)

    now = timezone.now()
    for action in initial:
        action.attempts += 1
        if action.attempts == 1:
            _send(action, messages.watch_retrying(process.source))
        elif action.attempts == FAST_RETRY_ATTEMPTS:
            _send(action, messages.watch_gave_up(process.source))
        # Depois das tentativas rápidas, respeita a cadência normal (Princípio II).
        delay = (
            settings.TELEGRAM_CHECK_COOLDOWN_SECONDS
            if action.attempts < FAST_RETRY_ATTEMPTS
            else settings.CHECK_INTERVAL_SECONDS
        )
        action.next_attempt_at = now + timedelta(seconds=delay)
        action.result_message = (process.last_error or 'Falha ao consultar o SEI')[:2000]
        action.save(update_fields=['attempts', 'next_attempt_at', 'result_message'])


def _handle_not_found(process: MonitoredProcess, actions: list[BotAction]) -> None:
    """Processo inexistente/não público: desfaz as assinaturas criadas pelo /watch."""
    for action in actions:
        process.subscriptions.filter(subscriber_id=action.chat.subscriber_id).delete()
        _finish(action, messages.watch_not_found(process.source), status=BotActionStatus.FAILED)

    if process.origin == ProcessOrigin.TELEGRAM and not process.has_baseline and not process.subscriptions.exists():
        logger.info('[telegram] Removendo processo #%d (%s): não encontrado no SEI.', process.pk, process.source)
        process.delete()
    else:
        recalculate_process_status(process)


def _finish(action: BotAction, text: str, status: str = BotActionStatus.DONE, send: bool = True) -> None:
    if send:
        _send(action, text)
    action.status = status
    action.attempts += 1
    action.finished_at = timezone.now()
    action.result_message = text[:2000]
    action.save(update_fields=['status', 'attempts', 'finished_at', 'result_message'])


def _send(action: BotAction, text: str) -> None:
    if action.chat.is_reachable:
        reply(action.chat, text)

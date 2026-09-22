"""
Serviço de monitoramento.

Orquestra a checagem de um processo: busca snapshot, compara hash,
cria DetectedChange e agenda notificações.

Design deliberado:
  - Função check_run_process() é o ponto de entrada único.
  - Cada etapa é uma função privada pequena e testável.
  - Não chama serviços externos diretamente — delega para clients.py.
  - Não conhece detalhes de e-mail/WhatsApp — delega para notifications.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.processes.models import MonitoredProcess, ProcessStatus

from .cache import get_hash_and_ttl, renew_ttl_if_needed, set_hash
from .clients import FetchError, Snapshot, collect_new_documents, get_snapshot
from .diff import compute_diff
from .models import (
    CheckRun,
    CheckStatus,
    DetectedChange,
    DetectedDocument,
    DetectedDocumentMode,
    DetectedDocumentStatus,
    PageSnapshot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------


def run_check(process: MonitoredProcess, notify_initial: bool = False) -> dict:
    """
    Executa uma checagem completa de um processo monitorado.

    Fluxo:
      1. Cria CheckRun com status=STARTED
      2. Busca snapshot da página via clients.get_snapshot()
      3. Compara hash com o último conhecido
      4. Se mudou: cria PageSnapshot, DetectedChange, agenda notificações
      5. Atualiza status do processo
      6. Finaliza CheckRun com status adequado

    Retorna dict com: ok (bool), changed (bool), message (str), check_run_id (int).
    """
    logger.info('[check] Iniciando #%d: %s', process.pk, process.label)

    try:
        snapshot_data = get_snapshot(
            source=process.effective_url,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            user_agent=settings.USER_AGENT,
        )
    except FetchError as exc:
        error_msg = str(exc)
        check_run = CheckRun.objects.create(process=process, status=CheckStatus.STARTED)
        _mark_failed(check_run, process, error_msg)
        logger.warning('[check] Falha em #%d: %s', process.pk, error_msg)
        return {'ok': False, 'changed': False, 'message': error_msg, 'check_run_id': check_run.pk}

    invalid_reason = _invalid_page_reason(process, snapshot_data)
    if invalid_reason:
        check_run = CheckRun.objects.create(process=process, status=CheckStatus.STARTED)
        _mark_failed(check_run, process, invalid_reason)
        logger.warning('[check] Snapshot inválido em #%d: %s', process.pk, invalid_reason)
        return {'ok': False, 'changed': False, 'message': invalid_reason, 'check_run_id': check_run.pk}

    cached_hash, ttl_remaining = get_hash_and_ttl(process.pk)
    if cached_hash and snapshot_data.content_hash == cached_hash:
        renewed = renew_ttl_if_needed(process.pk, ttl_remaining)
        _touch_process_no_change(process)
        logger.info(
            '[check] Sem mudança em #%d (cache Redis). TTL=%ss%s',
            process.pk,
            ttl_remaining,
            ' [renovado]' if renewed else '',
        )
        return {'ok': True, 'changed': False, 'message': 'Sem mudança detectada.', 'check_run_id': None}

    # ---- Primeira leitura: estabelece baseline ----
    if not process.last_hash:
        result = _handle_first_snapshot(process, snapshot_data, notify_initial)
        set_hash(process.pk, snapshot_data.content_hash)
        return result

    # ---- Sem mudança ----
    if snapshot_data.content_hash == process.last_hash:
        set_hash(process.pk, snapshot_data.content_hash)
        _touch_process_no_change(process)
        logger.info('[check] Sem mudança em #%d (hash do banco).', process.pk)
        return {'ok': True, 'changed': False, 'message': 'Sem mudança detectada.', 'check_run_id': None}

    # ---- Mudança detectada ----
    result = _handle_change(process, snapshot_data)
    if result.get('ok') and result.get('changed'):
        set_hash(process.pk, snapshot_data.content_hash)
    return result


def run_check_for_due_processes(max_processes: int | None = None) -> list[dict]:
    """Checa todos os processos ativos com checagem vencida e retorna os resultados."""
    from .scheduler import get_due_processes

    processes = get_due_processes(max_processes or settings.MAX_PROCESSES_PER_CYCLE)
    results: list[dict] = []
    for process in processes:
        result = run_check(process)
        result['process_id'] = process.pk
        result['label'] = process.label
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Handlers por caso
# ---------------------------------------------------------------------------


def _handle_first_snapshot(
    process: MonitoredProcess,
    snapshot_data: Snapshot,
    notify_initial: bool,
) -> dict:
    check_run = CheckRun.objects.create(process=process, status=CheckStatus.STARTED)
    snapshot = PageSnapshot.objects.create(
        process=process,
        check_run=check_run,
        content_hash=snapshot_data.content_hash,
        text_content=snapshot_data.text,
    )

    if notify_initial:
        change = DetectedChange.objects.create(
            process=process,
            check_run=check_run,
            new_snapshot=snapshot,
            new_hash=snapshot_data.content_hash,
            summary='Primeira leitura registrada como linha de base.',
            diff_text=snapshot_data.text[:8000],
        )
        _schedule_notifications(change)
        changed = True
    else:
        _update_process_baseline(process, snapshot_data.content_hash, snapshot_data.text)
        changed = False

    check_run.status = CheckStatus.SUCCESS
    check_run.finished_at = timezone.now()
    check_run.save(update_fields=['status', 'finished_at'])

    logger.info('[check] Baseline registrada para #%d.', process.pk)
    return {
        'ok': True,
        'changed': changed,
        'message': 'Primeira leitura registrada.',
        'check_run_id': check_run.pk,
    }


def _handle_change(
    process: MonitoredProcess,
    snapshot_data: Snapshot,
) -> dict:
    check_run = CheckRun.objects.create(process=process, status=CheckStatus.STARTED)
    old_text = process.last_text
    summary, diff_text = compute_diff(old_text, snapshot_data.text)

    document_results: list[dict[str, object]] = []

    # Tenta baixar documentos novos encontrados nos protocolos
    try:
        document_results = collect_new_documents(
            old_text=old_text,
            snapshot=snapshot_data,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            user_agent=settings.USER_AGENT,
        )
        if document_results:
            extra: list[str] = []
            downloaded = [item for item in document_results if item.get('status') == 'downloaded']
            pending = [item for item in document_results if item.get('status') == 'pending_retry']
            link_only = [item for item in document_results if item.get('status') == 'link_only']

            if downloaded:
                extra.append('Documentos baixados nesta leitura:')
                extra.extend(
                    f'- {item.get("document")}: {item.get("title")} ({item.get("url")})'
                    for item in downloaded
                )
            if link_only:
                extra.append('Documentos compactados (somente link):')
                extra.extend(
                    f'- {item.get("document")}: {item.get("error")} ({item.get("url")})'
                    for item in link_only
                )
            if pending:
                extra.append('Documentos pendentes para retentativa:')
                extra.extend(
                    f'- {item.get("document")}: {item.get("error")} ({item.get("url")})'
                    for item in pending
                )
            diff_text = (diff_text + '\n\n' + '\n'.join(extra))[:8000]
    except Exception as exc:
        logger.warning('[check] Falha ao coletar documentos para #%d: %s', process.pk, exc)

    # Recupera o último snapshot salvo para vinculação
    old_snapshot = PageSnapshot.objects.filter(process=process).order_by('-fetched_at').first()

    new_snapshot = PageSnapshot.objects.create(
        process=process,
        check_run=check_run,
        content_hash=snapshot_data.content_hash,
        text_content=snapshot_data.text,
    )

    change = DetectedChange.objects.create(
        process=process,
        check_run=check_run,
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        old_hash=process.last_hash,
        new_hash=snapshot_data.content_hash,
        summary=summary,
        diff_text=diff_text,
    )

    _persist_detected_documents(change, document_results)

    _update_process_after_change(process, snapshot_data.content_hash, snapshot_data.text)
    _schedule_notifications(change)

    check_run.status = CheckStatus.CHANGED
    check_run.finished_at = timezone.now()
    check_run.save(update_fields=['status', 'finished_at'])

    logger.info('[check] Mudança detectada em #%d: %s', process.pk, summary[:200])
    return {'ok': True, 'changed': True, 'message': summary, 'check_run_id': check_run.pk}


def _persist_detected_documents(change: DetectedChange, document_results: list[dict[str, object]]) -> None:
    if not document_results:
        return

    for item in document_results:
        doc_number = str(item.get('document') or '').strip()
        if not doc_number:
            continue

        mode = (
            DetectedDocumentMode.LINK_ONLY
            if item.get('mode') == 'link_only'
            else DetectedDocumentMode.ATTACHMENT
        )
        status = DetectedDocumentStatus.PENDING_RETRY
        if item.get('status') == 'link_only':
            status = DetectedDocumentStatus.LINK_ONLY_NOTIFIED
        elif item.get('status') == 'downloaded':
            # O download no monitor é apenas pré-validação; entrega ocorre por canal depois.
            status = DetectedDocumentStatus.PENDING_RETRY

        DetectedDocument.objects.create(
            change=change,
            document_number=doc_number,
            title=str(item.get('title') or '')[:240],
            url=str(item.get('url') or ''),
            mode=mode,
            status=status,
            retryable=bool(item.get('retryable', True)),
            failure_reason=str(item.get('error') or '')[:2000],
        )


# ---------------------------------------------------------------------------
# Helpers de estado
# ---------------------------------------------------------------------------


def _mark_failed(check_run: CheckRun, process: MonitoredProcess, error: str) -> None:
    check_run.status = CheckStatus.FAILED
    check_run.finished_at = timezone.now()
    check_run.error_message = error[:2000]
    check_run.save(update_fields=['status', 'finished_at', 'error_message'])
    process.last_error = error[:2000]
    process.last_checked_at = timezone.now()
    process.status = ProcessStatus.ERROR
    process.save(update_fields=['last_error', 'last_checked_at', 'status'])


def _mark_no_change(check_run: CheckRun, process: MonitoredProcess) -> None:
    check_run.status = CheckStatus.NO_CHANGE
    check_run.finished_at = timezone.now()
    check_run.save(update_fields=['status', 'finished_at'])
    process.last_checked_at = timezone.now()
    process.status = ProcessStatus.ACTIVE
    process.last_error = ''
    process.save(update_fields=['last_checked_at', 'status', 'last_error'])


def _touch_process_no_change(process: MonitoredProcess) -> None:
    process.last_checked_at = timezone.now()
    process.status = ProcessStatus.ACTIVE
    process.last_error = ''
    process.save(update_fields=['last_checked_at', 'status', 'last_error'])


def _update_process_baseline(process: MonitoredProcess, content_hash: str, text: str) -> None:
    process.last_hash = content_hash
    process.last_text = text
    process.last_checked_at = timezone.now()
    process.status = ProcessStatus.ACTIVE
    process.last_error = ''
    process.save(update_fields=['last_hash', 'last_text', 'last_checked_at', 'status', 'last_error'])


def _update_process_after_change(process: MonitoredProcess, content_hash: str, text: str) -> None:
    process.last_hash = content_hash
    process.last_text = text
    process.last_checked_at = timezone.now()
    process.last_changed_at = timezone.now()
    process.status = ProcessStatus.ACTIVE
    process.last_error = ''
    process.save(update_fields=[
        'last_hash', 'last_text', 'last_checked_at', 'last_changed_at', 'status', 'last_error',
    ])


def _schedule_notifications(change: DetectedChange) -> None:
    """Cria registros de Notification pendentes. Falhas são logadas, não propagadas."""
    from apps.notifications.services import create_notifications_for_change
    try:
        create_notifications_for_change(change)
    except Exception as exc:
        logger.error('[check] Erro ao criar notificações para mudança #%d: %s', change.pk, exc)


def _invalid_page_reason(process: MonitoredProcess, snapshot: Snapshot) -> str | None:
    text = (snapshot.text or '').strip()
    lowered = text.lower()
    lowered_title = (snapshot.title or '').lower()
    haystack = f'{lowered_title}\n{lowered}'

    invalid_tokens = (
        'captcha',
        'acesso negado',
        'forbidden',
        'access denied',
        'blocked',
        'cloudflare',
        'service unavailable',
        'temporariamente indisponivel',
        'internal server error',
        'erro interno do servidor',
    )
    for token in invalid_tokens:
        if token in haystack:
            return f'Página inválida detectada ({token}). Alteração ignorada.'

    min_len = int(getattr(settings, 'MIN_VALID_PAGE_TEXT_LENGTH', 220))
    if process.last_hash and len(process.last_text or '') > 300 and len(text) < min_len:
        return 'Conteúdo insuficiente para validar atualização da página.'

    markers = ('lista de andamentos', 'lista de protocolos')
    has_marker = any(marker in lowered for marker in markers)
    if process.last_text and len(process.last_text) > 500 and not has_marker:
        return 'Página sem seções esperadas (andamentos/protocolos). Possível bloqueio/incompleto.'

    if process.last_text and len(process.last_text) > 300:
        min_ratio = float(getattr(settings, 'MIN_VALID_PAGE_SIZE_RATIO', 0.35))
        old_len = max(1, len(process.last_text))
        ratio = len(text) / old_len
        if ratio < min_ratio:
            return 'Conteúdo possivelmente incompleto: tamanho muito abaixo do histórico.'

    return None

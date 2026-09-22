"""
Serviço de notificações.

Responsabilidades:
  - Criar registros de Notification a partir de uma DetectedChange
  - Despachar notificações pendentes para os canais corretos
  - Montar mensagens humanizadas para e-mail, WhatsApp e Telegram
  - Registrar tentativas com status e erro

Design: sem fila pesada. O envio é sequencial dentro de um ciclo do worker.
Se falhar, a notificação permanece PENDING e é retentada no próximo ciclo,
até atingir MAX_NOTIFICATION_ATTEMPTS.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.monitoring.clients import FetchError, _safe_document_filename, download_document
from apps.monitoring.extractors import (
    new_movement_records,
    new_protocol_records,
    related_process_mentions,
    relevant_movement_records,
)
from apps.monitoring.models import DetectedChange

from .models import (
    Notification,
    NotificationAttempt,
    NotificationChannel,
    NotificationDocumentState,
    NotificationDocumentStatus,
    NotificationStatus,
)

logger = logging.getLogger(__name__)


def _format_unresolved_docs(unresolved_docs: list[dict[str, str]], max_items: int = 12) -> str:
    lines: list[str] = []
    for item in unresolved_docs[:max_items]:
        doc = item.get('document') or 'Documento'
        reason = item.get('reason') or 'Falha no anexo'
        url = item.get('url') or ''
        suffix = f' | Link: {url}' if url else ''
        lines.append(f'- {doc}: {reason}{suffix}')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Criação de notificações
# ---------------------------------------------------------------------------


def create_notifications_for_change(change: DetectedChange) -> list[Notification]:
    """
    Para cada assinante ativo do processo que sofreu a mudança,
    cria um registro de Notification por canal habilitado.
    """
    from apps.subscribers.models import ProcessSubscription

    subscriptions = (
        ProcessSubscription.objects
        .filter(process=change.process)
        .select_related('subscriber', 'subscriber__telegram_chat')
    )
    created: list[Notification] = []

    for sub in subscriptions:
        subscriber = sub.subscriber
        # paused = /pause do bot, vale para todos os canais daquela assinatura.
        if sub.paused or not subscriber.is_reachable():
            continue

        # Canal e-mail
        if sub.email_enabled and subscriber.email_enabled and subscriber.email:
            notification = Notification.objects.create(
                change=change,
                subscriber=subscriber,
                channel=NotificationChannel.EMAIL,
                destination=subscriber.email,
                status=NotificationStatus.PENDING,
            )
            _create_document_states(notification)
            created.append(notification)

        # Canal Telegram (canal principal; destino = chat_id do TelegramChat)
        telegram_chat = getattr(subscriber, 'telegram_chat', None)
        if (
            sub.telegram_enabled
            and settings.TELEGRAM_ENABLED
            and telegram_chat is not None
            and telegram_chat.is_reachable
        ):
            notification = Notification.objects.create(
                change=change,
                subscriber=subscriber,
                channel=NotificationChannel.TELEGRAM,
                destination=str(telegram_chat.chat_id),
                status=NotificationStatus.PENDING,
            )
            _create_document_states(notification)
            created.append(notification)

        # Canal WhatsApp (só cria se Evolution API estiver habilitada globalmente)
        if (
            sub.whatsapp_enabled
            and subscriber.whatsapp_enabled
            and subscriber.phone
            and settings.EVOLUTION_ENABLED
        ):
            notification = Notification.objects.create(
                change=change,
                subscriber=subscriber,
                channel=NotificationChannel.WHATSAPP,
                destination=subscriber.phone,
                status=NotificationStatus.PENDING,
            )
            _create_document_states(notification)
            created.append(notification)

    logger.info(
        '[notify] %d notificação(ões) criada(s) para mudança #%d (%s).',
        len(created), change.pk, change.process.label,
    )
    return created


# ---------------------------------------------------------------------------
# Envio de notificações pendentes
# ---------------------------------------------------------------------------


def send_pending_notifications(max_attempts: int | None = None) -> dict:
    """
    Processa todas as notificações com status PENDING que ainda têm tentativas.
    Retorna estatísticas do ciclo: {total, sent, failed, skipped, pending}.
    """
    limit = max_attempts or settings.MAX_NOTIFICATION_ATTEMPTS
    pending = (
        Notification.objects
        .filter(status=NotificationStatus.PENDING, attempts__lt=limit)
        .select_related('change', 'change__process', 'subscriber')
    )

    stats: dict[str, int] = {'total': pending.count(), 'sent': 0, 'failed': 0, 'skipped': 0, 'pending': 0}
    for notification in pending:
        result_status = dispatch_notification(notification)
        stats[result_status] = stats.get(result_status, 0) + 1

    return stats


def dispatch_notification(notification: Notification) -> str:
    """
    Envia uma única notificação. Atualiza seu status e registra a tentativa.
    Retorna o status resultante (string).
    """
    notification.attempts += 1
    include_main_message = notification.sent_at is None
    change = notification.change
    process = change.process
    max_attempts = int(getattr(settings, 'MAX_NOTIFICATION_ATTEMPTS', 3))

    states = list(notification.document_states.select_related('document').all())
    attachment_candidates, unresolved_docs = _prepare_attachments_for_channel(notification, states)

    status, error = _dispatch_payload(
        notification=notification,
        include_main_message=include_main_message,
        attachment_candidates=attachment_candidates,
        unresolved_docs=unresolved_docs,
    )

    if status == NotificationStatus.SENT:
        if notification.sent_at is None:
            notification.sent_at = timezone.now()
        _mark_state_candidates_sent(attachment_candidates)

    pending_states = notification.document_states.filter(status=NotificationDocumentStatus.PENDING).exists()
    if status == NotificationStatus.SENT and pending_states:
        if notification.attempts >= max_attempts:
            notification.status = NotificationStatus.SENT
            unresolved = _pending_document_summaries(notification)
            notification.error_message = (f'Anexos pendentes após limite de tentativas: {unresolved}')[:2000]
        else:
            notification.status = NotificationStatus.PENDING
            notification.error_message = (
                'Notificação principal enviada; aguardando retentativa de anexos pendentes.'
            )
    else:
        notification.status = status
        notification.error_message = (error or '')[:2000]

    if notification.attempts >= max_attempts and notification.sent_at is None and notification.status == NotificationStatus.PENDING:
        notification.status = NotificationStatus.FAILED
        notification.error_message = 'Falha ao enviar notificação principal dentro do limite de tentativas.'

    notification.save(update_fields=['status', 'error_message', 'sent_at', 'attempts'])

    NotificationAttempt.objects.create(
        notification=notification,
        status=status,
        error=notification.error_message,
    )

    log_fn = logger.info if notification.status in (NotificationStatus.SENT, NotificationStatus.PENDING) else logger.warning
    log_fn(
        '[notify] [%s] %s -> %s%s',
        notification.channel,
        notification.destination,
        notification.status,
        f' ({notification.error_message})' if notification.error_message else '',
    )
    return notification.status


def _dispatch_payload(
    notification: Notification,
    include_main_message: bool,
    attachment_candidates: list[dict[str, object]],
    unresolved_docs: list[dict[str, str]],
) -> tuple[str, str | None]:
    process = notification.change.process
    is_complement = not include_main_message

    if notification.channel == NotificationChannel.EMAIL:
        from .channels.email import send_email_notification

        if include_main_message:
            subject = f'[CADE Monitor] Movimentação detectada: {process.label}'[:180]
            body = _build_body(process, notification.change, notification.channel, unresolved_docs)
        else:
            if not attachment_candidates:
                return NotificationStatus.SENT, None
            subject = f'[CADE Monitor] Complemento de anexos: {process.label}'[:180]
            body = _build_complement_body(process, notification.change, unresolved_docs)

        status, error = send_email_notification(
            to_address=notification.destination,
            subject=subject,
            body=body,
            attachments=[item['attachment'] for item in attachment_candidates],
        )
        return status, error

    if notification.channel == NotificationChannel.WHATSAPP:
        from .channels.evolution import send_whatsapp_attachment, send_whatsapp_notification

        if include_main_message:
            status, error = send_whatsapp_notification(
                phone=notification.destination,
                body=_build_body(process, notification.change, notification.channel, unresolved_docs),
            )
            if status != NotificationStatus.SENT:
                return status, error
        elif not attachment_candidates:
            return NotificationStatus.SENT, None
        else:
            comp_status, comp_error = send_whatsapp_notification(
                phone=notification.destination,
                body=_build_complement_body(process, notification.change, unresolved_docs),
            )
            if comp_status != NotificationStatus.SENT:
                return comp_status, comp_error

        # Mensagens de anexo devem ser enviadas sem texto adicional.
        failed_media: list[str] = []
        sent_any = False
        for item in attachment_candidates:
            state = item['state']
            attachment = item['attachment']
            media_status, media_error = send_whatsapp_attachment(
                phone=notification.destination,
                media_url=str(attachment.get('url') or ''),
                file_name=str(attachment.get('filename') or 'documento'),
            )
            if media_status == NotificationStatus.SENT:
                sent_any = True
                continue
            _mark_state_pending(state, media_error or 'Falha ao enviar anexo via WhatsApp')
            failed_media.append(str(attachment.get('filename') or attachment.get('document') or 'documento'))

        if failed_media and not sent_any:
            return NotificationStatus.PENDING, 'Falha no envio de anexos via WhatsApp.'
        if failed_media and sent_any:
            return NotificationStatus.PENDING, 'Parte dos anexos WhatsApp será reenviada automaticamente.'
        return NotificationStatus.SENT, None

    if notification.channel == NotificationChannel.TELEGRAM:
        return _dispatch_telegram(
            notification, process, include_main_message, attachment_candidates, unresolved_docs,
        )

    return NotificationStatus.SKIPPED, f'Canal desconhecido: {notification.channel}'


def _dispatch_telegram(
    notification: Notification,
    process,
    include_main_message: bool,
    attachment_candidates: list[dict[str, object]],
    unresolved_docs: list[dict[str, str]],
) -> tuple[str, str | None]:
    """Mesmo fluxo do WhatsApp: mensagem principal (ou complemento) + anexos por URL."""
    from .channels.telegram import send_telegram_document, send_telegram_message

    if include_main_message:
        body = _build_body(process, notification.change, notification.channel, unresolved_docs)
    elif not attachment_candidates:
        return NotificationStatus.SENT, None
    else:
        body = _build_complement_body(process, notification.change, unresolved_docs)

    status, error = send_telegram_message(notification.destination, body, process_url=process.effective_url)
    if status != NotificationStatus.SENT:
        return status, error

    failed_docs: list[str] = []
    sent_any = False
    for item in attachment_candidates:
        attachment = item['attachment']
        doc_status, doc_error = send_telegram_document(
            chat_id=notification.destination,
            document_url=str(attachment.get('url') or ''),
            filename=str(attachment.get('filename') or 'documento'),
        )
        if doc_status == NotificationStatus.SENT:
            sent_any = True
            continue
        _mark_state_pending(item['state'], doc_error or 'Falha ao enviar anexo via Telegram')
        failed_docs.append(str(attachment.get('filename') or attachment.get('document') or 'documento'))

    if failed_docs and not sent_any:
        return NotificationStatus.PENDING, 'Falha no envio de anexos via Telegram.'
    if failed_docs:
        return NotificationStatus.PENDING, 'Parte dos anexos do Telegram será reenviada automaticamente.'
    return NotificationStatus.SENT, None


def _create_document_states(notification: Notification) -> None:
    documents = notification.change.documents.all()
    for document in documents:
        NotificationDocumentState.objects.get_or_create(
            notification=notification,
            document=document,
            defaults={
                'status': (
                    NotificationDocumentStatus.SENT
                    if document.mode == 'link_only'
                    else NotificationDocumentStatus.PENDING
                ),
                'last_error': document.failure_reason[:2000],
            },
        )


def _prepare_attachments_for_channel(
    notification: Notification,
    states: list[NotificationDocumentState],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    attachment_candidates: list[dict[str, object]] = []
    unresolved_docs: list[dict[str, str]] = []

    max_bytes = (
        int(getattr(settings, 'EMAIL_ATTACHMENT_MAX_BYTES', 8 * 1024 * 1024))
        if notification.channel == NotificationChannel.EMAIL
        else int(getattr(settings, 'WHATSAPP_ATTACHMENT_MAX_BYTES', 8 * 1024 * 1024))
    )

    for state in states:
        doc = state.document
        if state.status != NotificationDocumentStatus.PENDING:
            continue

        if doc.mode == 'link_only':
            state.status = NotificationDocumentStatus.SENT
            state.last_error = (doc.failure_reason or 'Arquivo compactado: envio somente por link.')[:2000]
            state.sent_at = timezone.now()
            state.save(update_fields=['status', 'last_error', 'sent_at', 'updated_at'])
            unresolved_docs.append({
                'document': doc.document_number,
                'reason': state.last_error,
                'url': doc.url,
            })
            continue

        if not doc.url:
            _mark_state_pending(state, 'Documento sem link público para download no momento.')
            unresolved_docs.append({'document': doc.document_number, 'reason': state.last_error, 'url': ''})
            continue

        if notification.channel in (NotificationChannel.WHATSAPP, NotificationChannel.TELEGRAM):
            # A Evolution API e o Telegram recebem só a URL pública e buscam o arquivo do
            # lado deles — o conteúdo baixado aqui nunca seria usado, então não faz
            # sentido gastar banda/memória baixando o documento inteiro só para
            # descartar em seguida (spec 002-repo-hardening-cleanup, FR-009).
            filename = _safe_document_filename(doc.document_number, doc.title, '', doc.url)
            attachment_candidates.append({
                'state': state,
                'attachment': {
                    'document': doc.document_number,
                    'title': doc.title,
                    'filename': filename,
                    'url': doc.url,
                },
            })
            continue

        try:
            attachment = download_document(
                url=doc.url,
                record={'document': doc.document_number, 'doc_type': doc.title},
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
                user_agent=settings.USER_AGENT,
            )
        except FetchError as exc:
            _mark_state_pending(state, str(exc))
            unresolved_docs.append({'document': doc.document_number, 'reason': state.last_error, 'url': doc.url})
            continue

        content = attachment.get('content')
        size = len(content) if isinstance(content, (bytes, bytearray)) else 0
        if size > max_bytes:
            _mark_state_pending(
                state,
                f'Arquivo acima do limite técnico do canal ({max_bytes // (1024 * 1024)} MB).',
            )
            unresolved_docs.append({'document': doc.document_number, 'reason': state.last_error, 'url': doc.url})
            continue

        attachment_candidates.append({'state': state, 'attachment': attachment})

    return attachment_candidates, unresolved_docs


def _mark_state_pending(state: NotificationDocumentState, error: str) -> None:
    state.attempts += 1
    state.last_error = (error or '')[:2000]
    state.status = NotificationDocumentStatus.PENDING
    state.save(update_fields=['attempts', 'last_error', 'status', 'updated_at'])


def _mark_state_candidates_sent(candidates: list[dict[str, object]]) -> None:
    if not candidates:
        return
    now = timezone.now()
    for item in candidates:
        state: NotificationDocumentState = item['state']
        state.status = NotificationDocumentStatus.SENT
        state.sent_at = now
        state.last_error = ''
        state.attempts += 1
        state.save(update_fields=['status', 'sent_at', 'last_error', 'attempts', 'updated_at'])


def _pending_document_summaries(notification: Notification) -> str:
    pending = (
        notification.document_states
        .select_related('document')
        .filter(status=NotificationDocumentStatus.PENDING)
    )
    parts = [state.document.document_number or 'sem número' for state in pending[:8]]
    return ', '.join(parts)


# ---------------------------------------------------------------------------
# Montagem de mensagens humanizadas
# ---------------------------------------------------------------------------


def _build_body(process, change: DetectedChange, channel: str, unresolved_docs: list[dict[str, str]]) -> str:
    """
    Constrói a mensagem humanizada para o canal especificado.
    WhatsApp recebe versão compacta; e-mail recebe versão completa.
    """
    from django.utils.timezone import localtime
    detected_at = localtime(change.detected_at).strftime('%d/%m/%Y às %H:%M')
    process_url = process.effective_url
    old_text = change.old_snapshot.text_content if change.old_snapshot else ''
    new_text = change.new_snapshot.text_content if change.new_snapshot else ''
    new_docs = new_protocol_records(old_text, new_text)
    relevant_movements = relevant_movement_records(new_movement_records(old_text, new_text))
    relevant_count = len(new_docs) + len(relevant_movements)
    attached_count = change.documents.filter(mode='attachment').count() - len(unresolved_docs)
    not_attached_count = len(unresolved_docs)

    unresolved_lines = _format_unresolved_docs(unresolved_docs)

    related_refs: list[str] = []
    for movement in relevant_movements:
        for mention in related_process_mentions(movement.get('text', '')):
            if mention not in related_refs:
                related_refs.append(mention)

    documents = list(change.documents.all())
    return _build_hybrid_message(
        channel=channel,
        process_label=process.label,
        process_url=process_url,
        relevant_count=relevant_count,
        documents=documents,
        unresolved_lines=unresolved_lines,
        related_refs=related_refs,
        detected_at=detected_at,
        summary=change.summary,
        diff_text=change.diff_text,
        attached_count=max(0, attached_count),
        not_attached_count=not_attached_count,
    )


def build_test_notification_body(process_label: str, process_url: str, channel: str) -> str:
    """Gera mensagem de teste com o mesmo template híbrido da notificação normal."""
    from django.utils.timezone import localtime

    detected_at = localtime(timezone.now()).strftime('%d/%m/%Y às %H:%M')
    test_doc = {
        'document_number': 'TESTE',
        'title': 'Documento de teste',
        'url': process_url,
    }
    return _build_hybrid_message(
        channel=channel,
        process_label=process_label,
        process_url=process_url,
        relevant_count=1,
        documents=[test_doc],
        unresolved_lines='',
        related_refs=[],
        detected_at=detected_at,
        summary='Mensagem de teste do canal de notificação.',
        diff_text='',
        attached_count=1,
        not_attached_count=0,
        is_test=True,
    )


def _build_hybrid_message(
    *,
    channel: str,
    process_label: str,
    process_url: str,
    relevant_count: int,
    documents: list,
    unresolved_lines: str,
    related_refs: list[str],
    detected_at: str,
    summary: str,
    diff_text: str,
    attached_count: int,
    not_attached_count: int,
    is_test: bool = False,
) -> str:
    doc_lines: list[str] = []
    for doc in documents[:8]:
        if isinstance(doc, dict):
            doc_number = str(doc.get('document_number') or '').strip()
            title = str(doc.get('title') or 'Documento').strip()
            url = str(doc.get('url') or '').strip()
        else:
            doc_number = str(getattr(doc, 'document_number', '') or '').strip()
            title = str(getattr(doc, 'title', '') or 'Documento').strip()
            url = str(getattr(doc, 'url', '') or '').strip()
        label = f'{title} {doc_number}'.strip()

        doc_lines.append(f'- {label}')
        if url:
            if channel == NotificationChannel.EMAIL:
                doc_lines.append(f'  [abrir documento]({url})')
            else:
                doc_lines.append(f'  abrir documento: {url}')

    process_link = (
        f'[abrir processo]({process_url})'
        if channel == NotificationChannel.EMAIL
        else process_url
    )

    lines = [
        f'📁 Nome do Processo: {process_label}',
        '',
        f'🔎 O Cade Monitor detectou {relevant_count} movimentação(ões)/documento(s) relevante(s).',
        '',
        (
            '📄 Documento novo disponível no processo.'
            if not is_test
            else '🧪 Mensagem de teste do canal de notificação.'
        ),
        '',
    ]

    if doc_lines:
        lines.append('🆕 Documentos novos:')
        lines.extend(doc_lines)
        lines.append('')

    lines.extend([
        '🔗 Processo no SEI/CADE:',
        process_link,
        '',
        f'🕒 Detectado em: {detected_at}',
        f'📎 Anexos enviados: {attached_count}',
    ])

    if not_attached_count:
        lines.append(f'⚠️ Anexos não enviados: {not_attached_count}')
    if related_refs:
        lines.append(f'🧭 Referências a outros autos/processos: {", ".join(related_refs[:8])}')
    if unresolved_lines:
        lines.append('')
        lines.append('❗ Documentos não anexados:')
        lines.append(unresolved_lines)

    if channel == NotificationChannel.EMAIL and not is_test:
        lines.extend([
            '',
            'Resumo:',
            summary,
        ])
        if diff_text:
            lines.extend([
                '',
                'Detalhes:',
                diff_text,
            ])

    return '\n'.join(lines)


def _build_complement_body(process, change: DetectedChange, unresolved_docs: list[dict[str, str]]) -> str:
    from django.utils.timezone import localtime

    unresolved_lines = _format_unresolved_docs(unresolved_docs)
    detected_at = localtime(change.detected_at).strftime('%d/%m/%Y às %H:%M')
    return (
        f'📬 Complementação de anexos do processo {process.label}.\n\n'
        f'Esta mensagem não repete a notificação principal; envia apenas anexos pendentes ou status atualizado.\n'
        + (f'⚠️ Pendências atuais:\n{unresolved_lines}\n\n' if unresolved_lines else '')
        + f'🕒 Detectado originalmente em: {detected_at}'
    )

"""
Serviço de notificações.

Responsabilidades:
  - Criar registros de Notification a partir de uma DetectedChange
  - Despachar notificações pendentes para os canais corretos
  - Montar mensagens humanizadas para e-mail e WhatsApp
  - Registrar tentativas com status e erro

Design: sem fila pesada. O envio é sequencial dentro de um ciclo do worker.
Se falhar, a notificação permanece PENDING e é retentada no próximo ciclo,
até atingir MAX_NOTIFICATION_ATTEMPTS.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.monitoring.models import DetectedChange

from .models import Notification, NotificationAttempt, NotificationChannel, NotificationStatus

logger = logging.getLogger(__name__)


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
        .select_related('subscriber')
    )
    created: list[Notification] = []

    for sub in subscriptions:
        subscriber = sub.subscriber
        if not subscriber.is_reachable():
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
    Retorna estatísticas do ciclo: {total, sent, failed, skipped}.
    """
    limit = max_attempts or settings.MAX_NOTIFICATION_ATTEMPTS
    pending = (
        Notification.objects
        .filter(status=NotificationStatus.PENDING, attempts__lt=limit)
        .select_related('change', 'change__process', 'subscriber')
    )

    stats: dict[str, int] = {'total': pending.count(), 'sent': 0, 'failed': 0, 'skipped': 0}
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
    change = notification.change
    process = change.process

    body = _build_body(process, change, notification.channel)

    if notification.channel == NotificationChannel.EMAIL:
        from .channels.email import send_email_notification
        subject = f'[CADE Monitor] Movimentação detectada: {process.label}'[:180]
        status, error = send_email_notification(
            to_address=notification.destination,
            subject=subject,
            body=body,
        )

    elif notification.channel == NotificationChannel.WHATSAPP:
        from .channels.evolution import send_whatsapp_notification
        status, error = send_whatsapp_notification(
            phone=notification.destination,
            body=body,
        )

    else:
        status = 'skipped'
        error = f'Canal desconhecido: {notification.channel}'

    notification.status = status
    notification.error_message = (error or '')[:2000]
    if status == NotificationStatus.SENT:
        notification.sent_at = timezone.now()
    notification.save(update_fields=['status', 'error_message', 'sent_at', 'attempts'])

    NotificationAttempt.objects.create(
        notification=notification,
        status=status,
        error=notification.error_message,
    )

    log_fn = logger.info if status == 'sent' else logger.warning
    log_fn(
        '[notify] [%s] %s → %s%s',
        notification.channel,
        notification.destination,
        status,
        f' ({error})' if error else '',
    )
    return status


# ---------------------------------------------------------------------------
# Montagem de mensagens humanizadas
# ---------------------------------------------------------------------------


def _build_body(process, change: DetectedChange, channel: str) -> str:
    """
    Constrói a mensagem humanizada para o canal especificado.
    WhatsApp recebe versão compacta; e-mail recebe versão completa.
    """
    from django.utils.timezone import localtime
    detected_at = localtime(change.detected_at).strftime('%d/%m/%Y às %H:%M')
    process_url = process.effective_url

    if channel == NotificationChannel.WHATSAPP:
        return (
            f'Olá! O CADE Monitor encontrou uma nova alteração.\n\n'
            f'*Processo:* {process.label}\n\n'
            f'*Resumo:*\n{change.summary[:500]}\n\n'
            f'Detectado em: {detected_at}\n\n'
            f'Acesse o painel para ver o antes/depois em detalhes.'
        )

    return (
        f'Foi detectada uma movimentação ou alteração na página pública monitorada.\n\n'
        f'Processo: {process.label}\n'
        f'URL pública: {process_url}\n\n'
        f'Resumo:\n{change.summary}\n\n'
        f'Detalhes:\n{change.diff_text}\n\n'
        f'Observação: este alerta compara o conteúdo público extraído da página. '
        f'Confira a página oficial antes de tomar qualquer providência.\n\n'
        f'Detectado em: {detected_at}'
    )

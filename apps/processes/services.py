"""
Serviços do app processes.
Funções de escrita com regras de negócio de criação e atualização de processos.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from django.conf import settings

from .models import MonitoredProcess, ProcessStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManualDispatchChannel:
    """
    Um canal a tentar para cada assinatura, no fluxo de envio manual do painel.

    `is_eligible` decide se este canal deve ser tentado para uma dada
    assinatura (ex.: respeitar ou não o toggle por processo, checar
    EVOLUTION_ENABLED). `send` executa o envio para um assinante já elegível
    e retorna (status, mensagem_de_erro_ou_None) — o mesmo formato usado pelos
    canais em apps/notifications/channels/.
    """

    name: str
    is_eligible: Callable[[object], bool]
    send: Callable[[object], tuple[str, str | None]]


def dispatch_manual_notifications(subscriptions, channels: list[ManualDispatchChannel]) -> dict[str, dict]:
    """
    Percorre as assinaturas uma única vez, tentando cada canal elegível para
    cada assinante alcançável, e agrega envios/falhas por canal.

    Extraído para eliminar a duplicação que existia entre as quatro views de
    envio manual em apps/processes/views.py — teste de e-mail, teste de
    WhatsApp, aviso manual e reenvio da última atualização (spec
    002-repo-hardening-cleanup, FR-008). Cada view monta seus próprios
    `ManualDispatchChannel` (assunto/corpo/anexos variam por view) e só essa
    função concentra o laço de "para cada assinante, para cada canal
    elegível, envie e conte".
    """
    stats: dict[str, dict[str, object]] = {
        channel.name: {'sent': 0, 'failed': 0, 'failure_details': []}
        for channel in channels
    }
    for subscription in subscriptions:
        subscriber = subscription.subscriber
        if not subscriber.is_reachable():
            continue
        for channel in channels:
            if not channel.is_eligible(subscription):
                continue
            status, error = channel.send(subscriber)
            bucket = stats[channel.name]
            if status == 'sent':
                bucket['sent'] += 1
            else:
                bucket['failed'] += 1
                if error:
                    bucket['failure_details'].append(f'{subscriber.name}: {error}')
    return stats


def create_process(
    label: str,
    source: str,
    check_interval_seconds: int | None = None,
    notes: str = '',
) -> MonitoredProcess:
    """
    Cria um processo monitorado.
    Se a fonte for um número de processo, tenta resolver a URL automaticamente.
    """
    source = source.strip()
    label = (label.strip() or source)[:300]
    interval = max(1500, int(check_interval_seconds or settings.CHECK_INTERVAL_SECONDS))

    resolved_url = _try_resolve_url(source)

    process = MonitoredProcess.objects.create(
        label=label,
        source=source,
        resolved_url=resolved_url,
        status=ProcessStatus.ACTIVE,
        check_interval_seconds=interval,
        notes=notes.strip(),
    )
    logger.info('[process] Processo #%d criado: %s', process.pk, process.label)
    return process


def update_process_status(process: MonitoredProcess, status: str) -> MonitoredProcess:
    process.status = status
    process.save(update_fields=['status', 'updated_at'])
    return process


def refresh_process_url(process: MonitoredProcess) -> str | None:
    """Re-resolve a URL de um processo cadastrado por número."""
    url = _try_resolve_url(process.source, force=True)
    if url:
        process.resolved_url = url
        process.save(update_fields=['resolved_url', 'updated_at'])
    return url


def _try_resolve_url(source: str, force: bool = False) -> str:
    """
    Se source for URL, retorna ''.
    Se for número de processo, tenta resolver para URL pública.
    """
    parsed = urlparse(source)
    if parsed.scheme in ('http', 'https') and parsed.netloc:
        return ''  # já é uma URL, não precisa resolver

    try:
        from apps.monitoring.clients import resolve_process_url
        url = resolve_process_url(
            source,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            user_agent=settings.USER_AGENT,
        )
        if url:
            logger.info('[process] %r resolvido para %s', source, url)
            return url
    except Exception as exc:
        logger.warning('[process] Não foi possível resolver %r: %s', source, exc)
    return ''

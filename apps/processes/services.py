"""
Serviços do app processes.
Funções de escrita com regras de negócio de criação e atualização de processos.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from django.conf import settings

from .models import MonitoredProcess, ProcessStatus

logger = logging.getLogger(__name__)


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

"""
Orquestração do app autos (spec 012): pedido de pacote e processamento pelo
run_worker. Ver specs/012-autos-processo-pacote/contracts/autos.md.
"""
from __future__ import annotations

import logging
import os

from django.conf import settings
from django.utils import timezone

from . import selectors
from .builder import monta_pacote
from .models import AutosPackageJob

logger = logging.getLogger(__name__)


def request_package(process, user) -> AutosPackageJob:
    """FR-005: reaproveita um job em andamento (ou pronto e ainda válido) para o
    mesmo processo; cria um novo `queued` caso contrário."""
    existing = selectors.active_or_recent_job(process)
    if existing is not None:
        return existing
    return AutosPackageJob.objects.create(process=process, requested_by=user)


def _expire_stale_jobs(now) -> int:
    """FR-011: remove o arquivo e marca como expirado qualquer job `ready` cujo
    `expires_at` já passou."""
    expired = 0
    stale = AutosPackageJob.objects.filter(status=AutosPackageJob.Status.READY, expires_at__lte=now)
    for job in stale:
        if job.file_path:
            full_path = os.path.join(settings.MEDIA_ROOT, job.file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
        job.status = AutosPackageJob.Status.EXPIRED
        job.save(update_fields=['status', 'updated_at'])
        expired += 1
    return expired


def run_pending_packages(now) -> dict:
    """Chamada pelo run_worker: avança (até `AUTOS_MAX_DOCUMENTS_PER_TICK`
    documentos) o job `queued`/`processing` mais antigo, e expira pacotes
    prontos vencidos. Nunca lança exceção para o chamador."""
    expired = _expire_stale_jobs(now)

    job = (
        AutosPackageJob.objects
        .filter(status__in=[AutosPackageJob.Status.QUEUED, AutosPackageJob.Status.PROCESSING])
        .order_by('created_at')
        .first()
    )
    if job is None:
        return {'processed': False, 'expired': expired}

    if job.status == AutosPackageJob.Status.QUEUED:
        job.status = AutosPackageJob.Status.PROCESSING
        job.save(update_fields=['status', 'updated_at'])

    try:
        monta_pacote(
            job, settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT,
            max_documents=settings.AUTOS_MAX_DOCUMENTS_PER_TICK,
        )
    except Exception as exc:  # noqa: BLE001 — nunca derruba o ciclo do worker
        logger.error('[autos] Erro inesperado ao montar pacote #%s: %s', job.pk, exc, exc_info=True)
        job.status = AutosPackageJob.Status.FAILED
        job.error = f'Erro inesperado: {exc}'
        job.save(update_fields=['status', 'error', 'updated_at'])

    return {'processed': True, 'job_id': job.pk, 'status': job.status, 'expired': expired}

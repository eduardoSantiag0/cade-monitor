"""Queries reutilizáveis do app autos. Lógica de negócio fica em services.py."""
from __future__ import annotations

from django.utils import timezone

from .models import AutosPackageJob


def active_or_recent_job(process) -> AutosPackageJob | None:
    """Job em andamento (queued/processing), ou pronto e ainda não expirado, para
    este processo — usado para decidir se um novo pedido deve reaproveitar um
    existente (FR-005) e para a página do processo exibir o status atual."""
    job = (
        AutosPackageJob.objects.filter(process=process)
        .order_by('-created_at')
        .first()
    )
    if job is None:
        return None
    if job.status in (AutosPackageJob.Status.QUEUED, AutosPackageJob.Status.PROCESSING):
        return job
    if job.status == AutosPackageJob.Status.READY and job.expires_at and job.expires_at > timezone.now():
        return job
    return None

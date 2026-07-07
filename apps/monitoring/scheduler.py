"""
Selectors do app monitoring: determina quais processos precisam ser checados.
Funções puras de leitura — sem efeitos colaterais.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.processes.models import MonitoredProcess, ProcessStatus


def get_due_processes(limit: int | None = None) -> list[MonitoredProcess]:
    """
    Retorna processos ativos com checagem vencida, ordenados por prioridade:
      1. Nunca checados (last_checked_at IS NULL)
      2. Há mais tempo sem checagem
    """
    now = timezone.now()
    # Ordena pelo último check para dar prioridade aos mais antigos.
    # O limit * 3 é uma heurística para pegar mais candidatos antes de filtrar.
    candidates = (
        MonitoredProcess.objects
        .filter(status=ProcessStatus.ACTIVE)
        .order_by('last_checked_at')
    )
    if limit:
        candidates = candidates[: limit * 3]

    due: list[MonitoredProcess] = []
    for process in candidates:
        if _is_due(process, now):
            due.append(process)
            if limit and len(due) >= limit:
                break
    return due


def _is_due(process: MonitoredProcess, now) -> bool:
    """Retorna True se o processo deve ser checado agora."""
    if process.last_checked_at is None:
        return True
    interval = max(
        settings.CHECK_INTERVAL_SECONDS,
        int(process.check_interval_seconds or settings.CHECK_INTERVAL_SECONDS),
    )
    return now >= process.last_checked_at + timedelta(seconds=interval)

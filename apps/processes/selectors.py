"""
Selectors do app processes.
Funções puras de leitura que retornam querysets e objetos.
Não têm efeitos colaterais.
"""
from __future__ import annotations

from django.db.models import Count, QuerySet
from django.utils import timezone

from .models import MonitoredProcess, ProcessStatus


def get_all_processes() -> QuerySet:
    """Retorna todos os processos com contagens anotadas."""
    return (
        MonitoredProcess.objects
        .annotate(
            subscriber_count=Count('subscriptions', distinct=True),
            change_count=Count('changes', distinct=True),
        )
        .order_by('-last_changed_at', '-updated_at')
    )


def get_filtered_processes(status: str = '') -> QuerySet:
    """Retorna processos filtrados por status, com contagens."""
    qs = get_all_processes()
    if status and status in ProcessStatus.values:
        qs = qs.filter(status=status)
    return qs


def get_active_processes() -> QuerySet:
    return get_all_processes().filter(status=ProcessStatus.ACTIVE)


def get_process_by_id(process_id: int) -> MonitoredProcess | None:
    try:
        return (
            MonitoredProcess.objects
            .annotate(
                subscriber_count=Count('subscriptions', distinct=True),
                change_count=Count('changes', distinct=True),
            )
            .get(pk=process_id)
        )
    except MonitoredProcess.DoesNotExist:
        return None


def get_dashboard_stats() -> dict:
    from apps.monitoring.models import DetectedChange
    from apps.notifications.models import Notification, NotificationStatus

    today = timezone.localdate()
    return {
        'total_processes': MonitoredProcess.objects.count(),
        'active_processes': MonitoredProcess.objects.filter(status=ProcessStatus.ACTIVE).count(),
        'error_processes': MonitoredProcess.objects.filter(status=ProcessStatus.ERROR).count(),
        'changes_today': DetectedChange.objects.filter(detected_at__date=today).count(),
        'pending_notifications': Notification.objects.filter(
            status=NotificationStatus.PENDING
        ).count(),
    }

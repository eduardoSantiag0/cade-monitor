"""
Selectors do app telegram_bot: consultas de leitura, sem efeitos colaterais.
"""
from __future__ import annotations

from django.db.models import QuerySet

from apps.monitoring.extractors import latest_cade_records
from apps.monitoring.models import DetectedChange
from apps.processes.models import MonitoredProcess
from apps.subscribers.models import ProcessSubscription

from .models import TelegramChat


def chat_subscriptions(chat: TelegramChat) -> QuerySet:
    return (
        ProcessSubscription.objects
        .filter(subscriber_id=chat.subscriber_id)
        .select_related('process')
        .order_by('process__label')
    )


def find_chat_subscription(chat: TelegramChat, source: str) -> ProcessSubscription | None:
    """Assinatura do chat para o processo cujo `source` normalizado é `source`."""
    return chat_subscriptions(chat).filter(process__source=source).first()


def latest_records(process: MonitoredProcess, limit: int = 3) -> list[str]:
    return latest_cade_records(process.last_text, limit=limit)


def last_change(process: MonitoredProcess) -> DetectedChange | None:
    return process.changes.order_by('-detected_at').first()


def process_history(process: MonitoredProcess, limit: int) -> list[DetectedChange]:
    return list(process.changes.order_by('-detected_at')[:limit])

"""Queries reutilizáveis do app dou. Lógica de negócio fica em services.py."""
from __future__ import annotations

from datetime import date

from .models import DouSendLog, DouSubscription


def active_digest_subscriptions() -> list[DouSubscription]:
    return list(
        DouSubscription.objects.select_related('subscriber')
        .prefetch_related('monitored_terms')
        .filter(enabled=True)
    )


def active_anticipation_subscriptions() -> list[DouSubscription]:
    return list(
        DouSubscription.objects.select_related('subscriber')
        .prefetch_related('monitored_terms')
        .filter(nextday_enabled=True)
    )


def already_sent(subscription: DouSubscription, kind: str, reference_date: date) -> bool:
    return DouSendLog.objects.filter(
        subscription=subscription, kind=kind, reference_date=reference_date,
    ).exists()


def monitored_terms(subscription: DouSubscription) -> list[str]:
    return [t.term for t in subscription.monitored_terms.all()]

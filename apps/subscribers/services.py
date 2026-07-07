from __future__ import annotations

import logging

from .models import ProcessSubscription, Subscriber

logger = logging.getLogger(__name__)


def create_subscriber(
    name: str,
    email: str = '',
    phone: str = '',
    email_enabled: bool = True,
    whatsapp_enabled: bool = False,
) -> Subscriber:
    phone_clean = phone.strip().replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    subscriber = Subscriber.objects.create(
        name=name.strip(),
        email=email.strip(),
        phone=phone_clean,
        email_enabled=email_enabled,
        whatsapp_enabled=whatsapp_enabled,
    )
    logger.info('[subscriber] Assinante #%d criado: %s', subscriber.pk, subscriber.name)
    return subscriber


def add_subscription(
    subscriber: Subscriber,
    process,
    email_enabled: bool = True,
    whatsapp_enabled: bool = True,
) -> ProcessSubscription:
    sub, _ = ProcessSubscription.objects.get_or_create(
        subscriber=subscriber,
        process=process,
        defaults={'email_enabled': email_enabled, 'whatsapp_enabled': whatsapp_enabled},
    )
    return sub


def remove_subscription(subscriber: Subscriber, process) -> None:
    ProcessSubscription.objects.filter(subscriber=subscriber, process=process).delete()

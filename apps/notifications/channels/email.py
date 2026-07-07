"""
Canal de e-mail usando o sistema nativo do Django (django.core.mail).

Vantagem: usa EMAIL_BACKEND configurado no settings.py.
Em desenvolvimento, o console backend exibe os e-mails sem enviar.
Em produção, usa SMTP configurado via variáveis de ambiente.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def send_email_notification(
    to_address: str,
    subject: str,
    body: str,
    attachments: list[dict] | None = None,
) -> tuple[str, str | None]:
    """
    Envia e-mail usando django.core.mail.
    Retorna (status, error_message).
    """
    if not to_address or '@' not in to_address:
        return 'invalid_recipient', f'Endereço de e-mail inválido: {to_address!r}'

    from_email = settings.DEFAULT_FROM_EMAIL
    if not from_email or from_email == 'cade-monitor@example.com':
        # Não bloqueia envio, mas loga o aviso
        logger.warning('[email] DEFAULT_FROM_EMAIL não personalizado.')

    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[to_address],
        )

        for att in (attachments or []):
            content = att.get('content')
            if not isinstance(content, (bytes, bytearray)):
                continue
            filename = str(att.get('filename') or 'documento')[:140]
            content_type = str(att.get('content_type') or 'application/octet-stream')
            maintype, _, subtype = content_type.partition('/')
            if not subtype:
                maintype, subtype = 'application', 'octet-stream'
            msg.attach(filename, bytes(content), f'{maintype}/{subtype}')

        msg.send(fail_silently=False)
        logger.debug('[email] Mensagem enviada para %s', to_address)
        return 'sent', None

    except Exception as exc:
        error = str(exc)[:1000]
        logger.warning('[email] Falha ao enviar para %s: %s', to_address, error)
        return 'failed', error

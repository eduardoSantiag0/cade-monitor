"""
Canal de e-mail usando o sistema nativo do Django (django.core.mail).

Vantagem: usa EMAIL_BACKEND configurado no settings.py.
Em desenvolvimento, o console backend exibe os e-mails sem enviar.
Em produção, usa SMTP configurado via variáveis de ambiente.
"""
from __future__ import annotations

import logging
from email.mime.text import MIMEText

from django.conf import settings
from django.core.mail import EmailMessage
from pydantic import ValidationError

from ..schemas import EmailAttachment

logger = logging.getLogger(__name__)


def send_email_notification(
    to_address: str,
    subject: str,
    body: str,
    attachments: list[dict] | None = None,
    html: bool = False,
) -> tuple[str, str | None]:
    """
    Envia e-mail usando django.core.mail.
    `html=True` marca o corpo como HTML (`Content-Type: text/html`) — usado pelo
    digest DOU (spec 009), que precisa de negrito/destaque visual; sem isso o corpo
    sai sempre como texto puro, como antes.
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
        if html:
            msg.content_subtype = 'html'

        for att in (attachments or []):
            content = att.get('content')
            if not isinstance(content, (bytes, bytearray)):
                continue
            try:
                attachment = EmailAttachment(
                    filename=str(att.get('filename') or ''),
                    content_type=str(att.get('content_type') or ''),
                    content=bytes(content),
                )
            except ValidationError as exc:
                logger.warning('[email] Anexo inválido ignorado: %s', exc)
                continue
            maintype, _, subtype = attachment.content_type.partition('/')
            calendar_method = str(att.get('calendar_method') or '').strip().upper()
            if calendar_method in ('REQUEST', 'CANCEL'):
                # Convite de calendário (spec 011): o parâmetro `method` no
                # Content-Type é o que faz Gmail/Outlook mostrarem os botões de
                # Aceitar/Recusar — precisa de `set_param`, não dá para embutir
                # no `content_type` de EmailAttachment (viraria subtype inválido).
                part = MIMEText(attachment.content.decode('utf-8'), subtype, 'utf-8')
                part.set_param('method', calendar_method)
                part.add_header(
                    'Content-Disposition', 'attachment', filename=attachment.filename,
                )
                msg.attach(part)
            else:
                msg.attach(attachment.filename, attachment.content, f'{maintype}/{subtype}')

        msg.send(fail_silently=False)
        logger.debug('[email] Mensagem enviada para %s', to_address)
        return 'sent', None

    except Exception as exc:
        error = str(exc)[:1000]
        logger.warning('[email] Falha ao enviar para %s: %s', to_address, error)
        return 'failed', error

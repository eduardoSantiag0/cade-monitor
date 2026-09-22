"""
Canal Telegram (canal principal — spec 006).

Responsabilidade única: entregar texto/anexo a um chat e traduzir a resposta
da Bot API para (status, erro), no mesmo contrato dos outros canais.
A chamada HTTP em si fica em apps/telegram_bot/client.py.
"""
from __future__ import annotations

from django.conf import settings

from apps.telegram_bot import client

TRUNCATION_NOTE = '\n\n… (mensagem cortada)'


def send_telegram_message(chat_id: str, body: str, process_url: str = '') -> tuple[str, str | None]:
    if not settings.TELEGRAM_ENABLED or not settings.TELEGRAM_BOT_TOKEN:
        return 'channel_not_configured', 'Telegram desabilitado (TELEGRAM_ENABLED/TELEGRAM_BOT_TOKEN)'
    return _to_status(chat_id, client.send_message(chat_id, _fit(body, process_url)))


def send_telegram_document(chat_id: str, document_url: str, filename: str) -> tuple[str, str | None]:
    if not settings.TELEGRAM_ENABLED or not settings.TELEGRAM_BOT_TOKEN:
        return 'channel_not_configured', 'Telegram desabilitado (TELEGRAM_ENABLED/TELEGRAM_BOT_TOKEN)'
    if not document_url:
        return 'failed', 'Documento sem URL pública'
    return _to_status(chat_id, client.send_document(chat_id, document_url, filename))


def _fit(body: str, process_url: str) -> str:
    """Corta no limite do Telegram, preservando o link do processo no final."""
    limit = client.MAX_MESSAGE_LENGTH
    if len(body) <= limit:
        return body
    suffix = TRUNCATION_NOTE + (f'\n{process_url}' if process_url else '')
    return body[: limit - len(suffix)] + suffix


def _to_status(chat_id: str, result: client.TelegramResult) -> tuple[str, str | None]:
    if result.ok:
        return 'sent', None
    error = f'Telegram {result.error_code or "rede"}: {result.description}'[:2000]
    if result.is_blocked:
        from apps.telegram_bot.services import mark_chat_unreachable
        mark_chat_unreachable(chat_id)
        return 'invalid_recipient', error
    # Transitório (rede, 429 flood control, 5xx): 'pending' mantém a notificação na
    # fila e dispatch_notification retenta até MAX_NOTIFICATION_ATTEMPTS.
    if result.error_code is None or result.error_code == 429 or result.error_code >= 500:
        return 'pending', error
    return 'failed', error

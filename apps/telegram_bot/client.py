"""
Cliente mínimo da Telegram Bot API (stdlib urllib, sem SDK — constituição, Princípio V).

Responsabilidade única: fazer a chamada HTTP e devolver um TelegramResult.
Nunca lança por erro da API ou de rede, e nunca coloca o token em logs/erros.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = 'https://api.telegram.org'
MAX_MESSAGE_LENGTH = 4096

BOT_COMMANDS = [
    ('start', 'Apresentação e ajuda'),
    ('watch', 'Monitorar um processo: /watch 08700.005905/2026-38'),
    ('unwatch', 'Parar de monitorar um processo'),
    ('list', 'Processos que você acompanha'),
    ('status', 'Última movimentação conhecida'),
    ('check', 'Verificar um processo agora'),
    ('pause', 'Pausar alertas de um processo'),
    ('resume', 'Retomar alertas de um processo'),
    ('history', 'Últimas movimentações'),
    ('ultima', 'Última atualização com o PDF do documento'),
    ('help', 'Lista de comandos'),
]


@dataclass(frozen=True)
class TelegramResult:
    ok: bool
    result: Any = None
    error_code: int | None = None
    description: str = ''
    extra: dict = field(default_factory=dict)

    @property
    def is_blocked(self) -> bool:
        """Destinatário inalcançável: bot bloqueado, removido do grupo ou chat inexistente."""
        if self.error_code == 403:
            return True
        return self.error_code == 400 and 'chat not found' in self.description.lower()


def call(method: str, payload: dict | None = None) -> TelegramResult:
    """POST JSON para a Bot API. Erros viram TelegramResult(ok=False)."""
    return _post(method, json.dumps(payload or {}).encode('utf-8'), 'application/json')


def _post(method: str, body: bytes, content_type: str) -> TelegramResult:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return TelegramResult(ok=False, description='TELEGRAM_BOT_TOKEN não configurado')

    request = urllib.request.Request(
        f'{API_BASE}/bot{token}/{method}',
        data=body,
        method='POST',
        headers={'Content-Type': content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.TELEGRAM_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = _read_error_body(exc)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # str(exc) de URLError não inclui a URL (e, portanto, o token).
        logger.warning('[telegram] Falha de rede em %s: %s', method, exc.__class__.__name__)
        return TelegramResult(ok=False, description=f'Falha de rede: {exc.__class__.__name__}')

    if body.get('ok'):
        return TelegramResult(ok=True, result=body.get('result'))
    result = TelegramResult(
        ok=False,
        error_code=body.get('error_code'),
        description=str(body.get('description') or 'erro desconhecido'),
        extra=body.get('parameters') or {},
    )
    logger.warning('[telegram] %s falhou: %s %s', method, result.error_code, result.description)
    return result


def _read_error_body(exc: urllib.error.HTTPError) -> dict:
    try:
        return json.loads(exc.read().decode('utf-8'))
    except (ValueError, OSError):
        return {'ok': False, 'error_code': exc.code, 'description': f'HTTP {exc.code}'}


def send_message(chat_id: int | str, text: str) -> TelegramResult:
    # Texto puro: evita erros de escape com conteúdo vindo do SEI (<, &, _).
    return call('sendMessage', {
        'chat_id': chat_id,
        'text': text[:MAX_MESSAGE_LENGTH],
        'disable_web_page_preview': True,
    })


def send_document_file(
    chat_id: int | str,
    content: bytes,
    filename: str,
    content_type: str = 'application/octet-stream',
    caption: str = '',
) -> TelegramResult:
    """
    Upload do arquivo (multipart/form-data). Preferível ao envio por URL: a Bot API
    só busca URLs de PDF/GIF/ZIP, e o SEI costuma servir HTML ou exigir cabeçalhos.
    """
    boundary = f'cademonitor-{uuid.uuid4().hex}'
    fields = {'chat_id': str(chat_id)}
    if caption:
        fields['caption'] = caption[:1024]
    CRLF = b'\r\n'
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}'.encode() + CRLF
            + f'Content-Disposition: form-data; name="{name}"'.encode() + CRLF + CRLF
            + str(value).encode('utf-8') + CRLF
        )
    safe_name = ''.join(ch for ch in (filename or 'documento') if ch not in '"\r\n') or 'documento'
    parts.append(
        f'--{boundary}'.encode() + CRLF
        + f'Content-Disposition: form-data; name="document"; filename="{safe_name}"'.encode('utf-8') + CRLF
        + f'Content-Type: {content_type or "application/octet-stream"}'.encode() + CRLF + CRLF
        + content + CRLF
    )
    parts.append(f'--{boundary}--'.encode() + CRLF)
    return _post('sendDocument', b''.join(parts), f'multipart/form-data; boundary={boundary}')


def get_chat_member(chat_id: int | str, user_id: int) -> TelegramResult:
    return call('getChatMember', {'chat_id': chat_id, 'user_id': user_id})


def get_me() -> TelegramResult:
    return call('getMe')


def set_webhook(url: str, secret_token: str) -> TelegramResult:
    return call('setWebhook', {
        'url': url,
        'secret_token': secret_token,
        'allowed_updates': ['message', 'my_chat_member'],
    })


def delete_webhook() -> TelegramResult:
    return call('deleteWebhook')


def get_webhook_info() -> TelegramResult:
    return call('getWebhookInfo')


def set_my_commands() -> TelegramResult:
    return call('setMyCommands', {
        'commands': [{'command': c, 'description': d} for c, d in BOT_COMMANDS],
    })

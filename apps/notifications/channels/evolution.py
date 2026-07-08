"""
Canal WhatsApp via Evolution API.

Responsabilidade única: montar payload e chamar o endpoint HTTP.
Não contém regra de negócio do sistema — apenas sabe falar com a API.

Documentação Evolution API: https://doc.evolution-api.com/
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def send_whatsapp_notification(phone: str, body: str) -> tuple[str, str | None]:
    """
    Envia mensagem de texto para um número via Evolution API.

    Retorna (status, error_message) onde status é uma das constantes de
    NotificationStatus do app notifications.
    """
    if not settings.EVOLUTION_ENABLED:
        return 'channel_not_configured', 'Evolution API desabilitada (EVOLUTION_ENABLED=false)'

    if not settings.EVOLUTION_API_BASE_URL:
        return 'channel_not_configured', 'EVOLUTION_API_BASE_URL não configurado'

    if not settings.EVOLUTION_API_KEY:
        return 'channel_not_configured', 'Configure AUTHENTICATION_API_KEY ou EVOLUTION_API_KEY'

    phone = _normalize_phone(phone)
    if not phone:
        return 'invalid_recipient', f'Número de telefone inválido: {phone!r}'

    return _call_api(phone, body)


def _normalize_phone(phone: str) -> str:
    """Remove formatação do número, mantendo apenas dígitos."""
    cleaned = phone.strip().replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not cleaned.isdigit() or len(cleaned) < 10:
        return ''
    return cleaned


def _call_api(phone: str, body: str) -> tuple[str, str | None]:
    """Faz a chamada HTTP para a Evolution API e trata os erros conhecidos."""
    instance = settings.EVOLUTION_INSTANCE_NAME
    url = f'{settings.EVOLUTION_API_BASE_URL}/message/sendText/{instance}'

    payload = json.dumps({'number': phone, 'text': body}).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=payload,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'apikey': settings.EVOLUTION_API_KEY,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.EVOLUTION_TIMEOUT_SECONDS) as response:
            status_code = int(getattr(response, 'status', 200))
            if 200 <= status_code < 300:
                logger.debug('[evolution] Mensagem enviada para %s (HTTP %d)', phone, status_code)
                return 'sent', None
            body_resp = response.read(2000).decode('utf-8', errors='replace')
            return 'failed', f'HTTP {status_code}: {body_resp[:500]}'

    except urllib.error.HTTPError as exc:
        error_detail = ''
        try:
            error_detail = exc.read(2000).decode('utf-8', errors='replace')[:300]
        except Exception:
            pass

        logger.warning('[evolution] HTTP %d ao enviar para %s: %s', exc.code, phone, error_detail)
        if exc.code == 401:
            return 'failed', 'Chave de API inválida ou sem permissão (HTTP 401)'
        if exc.code == 404:
            return 'failed', f'Instância "{instance}" não encontrada na Evolution API (HTTP 404)'
        if exc.code == 422:
            return 'invalid_recipient', f'Número recusado pela Evolution API (HTTP 422): {error_detail}'
        return 'failed', f'HTTP {exc.code}: {error_detail}'

    except urllib.error.URLError as exc:
        logger.warning('[evolution] Falha de rede ao enviar para %s: %s', phone, exc.reason)
        return 'failed', f'Falha de rede: {exc.reason}'

    except TimeoutError:
        logger.warning('[evolution] Timeout ao enviar para %s', phone)
        return 'failed', 'Tempo esgotado ao chamar a Evolution API'

    except Exception as exc:
        logger.error('[evolution] Erro inesperado ao enviar para %s: %s', phone, exc)
        return 'failed', f'Erro inesperado: {str(exc)[:300]}'

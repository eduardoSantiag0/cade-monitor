from __future__ import annotations

import base64
import json
import mimetypes
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any

from .config import Config
from .scraper import CADE_SEARCH_URL, is_url_source


def movement_subject(process_label: str) -> str:
    return f'[Meskade] Movimentacao detectada: {process_label}'[:180]


def movement_body(process_label: str, public_url: str, summary: str, diff: str) -> str:
    if is_url_source(public_url):
        origin = f'URL publica: {public_url}'
    else:
        origin = f'Numero/protocolo: {public_url}\nPesquisa publica CADE: {CADE_SEARCH_URL}'
    return (
        f'Foi detectada uma movimentacao ou alteracao na pagina monitorada.\n\n'
        f'Processo: {process_label}\n'
        f'{origin}\n\n'
        f'Resumo:\n{summary}\n\n'
        f'Detalhes:\n{diff}\n\n'
        f'Observacao: este alerta compara o conteudo publico extraido da pagina. '
        f'Confira a pagina oficial antes de tomar qualquer providencia.'
    )


def clean_attachments(attachments: list[dict[str, object]] | None) -> list[dict[str, object]]:
    return [item for item in (attachments or []) if isinstance(item.get('content'), (bytes, bytearray))]


def attachment_filename(attachment: dict[str, object]) -> str:
    filename = str(attachment.get('filename') or attachment.get('document') or 'documento')
    return filename[:140]


def attachment_content_type(attachment: dict[str, object]) -> str:
    filename = attachment_filename(attachment)
    guessed = mimetypes.guess_type(filename)[0]
    return str(attachment.get('content_type') or guessed or 'application/octet-stream')


def send_email(
    cfg: Config,
    to_address: str,
    subject: str,
    body: str,
    attachments: list[dict[str, object]] | None = None,
) -> tuple[str, str | None]:
    if not cfg.mail_host or not cfg.mail_from:
        return 'skipped', 'SMTP_HOST e MAIL_FROM precisam estar configurados no .env'

    msg = EmailMessage()
    msg['From'] = cfg.mail_from
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.set_content(body)

    for attachment in clean_attachments(attachments):
        content = bytes(attachment['content'])
        filename = attachment_filename(attachment)
        content_type = attachment_content_type(attachment)
        maintype, _, subtype = content_type.partition('/')
        if not subtype:
            maintype, subtype = 'application'
            subtype = 'octet-stream'
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    try:
        if cfg.mail_ssl:
            smtp = smtplib.SMTP_SSL(cfg.mail_host, cfg.mail_port, timeout=30)
        else:
            smtp = smtplib.SMTP(cfg.mail_host, cfg.mail_port, timeout=30)
        with smtp:
            if cfg.mail_tls and not cfg.mail_ssl:
                smtp.starttls(context=ssl.create_default_context())
            if cfg.mail_user:
                smtp.login(cfg.mail_user, cfg.mail_password)
            smtp.send_message(msg)
        return 'sent', None
    except Exception as exc:
        return 'failed', str(exc)[:1000]


def send_whatsapp(
    cfg: Config,
    destination: str,
    body: str,
    attachments: list[dict[str, object]] | None = None,
) -> tuple[str, str | None]:
    provider = cfg.whatsapp_provider
    if not provider:
        return 'skipped', 'WHATSAPP_PROVIDER nao configurado'
    if provider != 'evolution':
        return 'failed', f'Provedor WhatsApp nao suportado: {provider}. Use apenas evolution.'
    status, error = send_whatsapp_evolution(cfg, destination, body)
    if status != 'sent' or not attachments:
        return status, error
    return 'sent', 'Texto enviado. Anexos nao sao suportados neste modulo via Evolution.'


def send_whatsapp_evolution(cfg: Config, destination: str, body: str) -> tuple[str, str | None]:
    if not cfg.evolution_enabled:
        return 'skipped', 'EVOLUTION_ENABLED=false'
    if not cfg.evolution_api_base_url:
        return 'skipped', 'EVOLUTION_API_BASE_URL nao configurado'
    if not cfg.evolution_api_key:
        return 'skipped', 'EVOLUTION_API_KEY nao configurado'

    phone = only_digits(destination)
    if not phone:
        return 'failed', 'Telefone WhatsApp invalido'

    url = f'{cfg.evolution_api_base_url}/message/sendText/{cfg.evolution_instance_name}'
    payload = {'number': phone, 'text': body[:3900]}
    headers = {'apikey': cfg.evolution_api_key}
    return request_json(url, payload, headers, cfg.evolution_timeout_seconds)


def only_digits(value: str) -> str:
    return ''.join(ch for ch in value if ch.isdigit())


def request_json_response(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
    basic_auth: tuple[str, str] | None = None,
) -> tuple[str, str | None, dict[str, Any] | None]:
    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=data, method='POST')
    request.add_header('Content-Type', 'application/json')
    for key, value in headers.items():
        request.add_header(key, value)
    if basic_auth:
        token = base64.b64encode(f'{basic_auth[0]}:{basic_auth[1]}'.encode('utf-8')).decode('ascii')
        request.add_header('Authorization', f'Basic {token}')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode('utf-8', errors='replace')
            parsed = json.loads(response_body) if response_body.strip() else {}
            if 200 <= response.status < 300:
                return 'sent', None, parsed
            return 'failed', f'HTTP {response.status}: {response_body[:900]}', parsed
    except urllib.error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')[:1000]
        return 'failed', f'HTTP {exc.code}: {details}', None
    except Exception as exc:
        return 'failed', str(exc)[:1000], None


def request_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
    basic_auth: tuple[str, str] | None = None,
) -> tuple[str, str | None]:
    status, error, _ = request_json_response(url, payload, headers, timeout, basic_auth)
    return status, error

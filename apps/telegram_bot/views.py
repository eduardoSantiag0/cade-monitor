"""
Webhook do Telegram. View fina: valida, garante idempotência e delega.
Contrato: specs/006-telegram-bot/contracts/webhook-and-ops.md
"""
import hmac
import json
import logging

import sentry_sdk
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services
from .models import TelegramUpdate

logger = logging.getLogger(__name__)

SECRET_HEADER = 'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'


@csrf_exempt
@require_POST
def telegram_webhook(request):
    if not settings.TELEGRAM_ENABLED:
        return HttpResponseNotFound()

    received = request.META.get(SECRET_HEADER, '')
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected or not hmac.compare_digest(received.encode(), expected.encode()):
        return HttpResponseForbidden()

    try:
        payload = json.loads(request.body)
        update_id = int(payload['update_id'])
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest()

    try:
        with transaction.atomic():
            TelegramUpdate.objects.create(update_id=update_id)
    except IntegrityError:
        return HttpResponse(status=200)  # reentrega: já processada

    try:
        services.handle_update(payload)
    except Exception as exc:
        # 200 mesmo assim: senão o Telegram reentrega para sempre um update que sempre falha.
        logger.error('[telegram] Erro ao processar update %s: %s', update_id, exc, exc_info=True)
        sentry_sdk.capture_exception(exc)

    return JsonResponse({'ok': True})

"""
Cache de hash por processo usando Redis.

Objetivo: acelerar a decisão de "sem mudança" e reduzir escrita no banco.
Falhas de Redis não interrompem o monitoramento.
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import redis
except Exception:  # pragma: no cover - ambiente sem pacote redis
    redis = None  # type: ignore[assignment]


def _enabled() -> bool:
    return bool(getattr(settings, 'PROCESS_HASH_REDIS_ENABLED', False)) and bool(
        getattr(settings, 'PROCESS_HASH_REDIS_URL', '')
    )


def _key(process_id: int) -> str:
    prefix = getattr(settings, 'PROCESS_HASH_REDIS_KEY_PREFIX', 'cade-monitor:process-hash')
    return f'{prefix}:{process_id}'


def _client():
    if not _enabled() or redis is None:
        return None
    url = getattr(settings, 'PROCESS_HASH_REDIS_URL', '')
    try:
        return redis.from_url(url, decode_responses=True)
    except Exception as exc:
        logger.warning('[cache] Falha ao inicializar Redis: %s', exc)
        return None


def get_hash_and_ttl(process_id: int) -> tuple[str | None, int | None]:
    client = _client()
    if client is None:
        return None, None
    key = _key(process_id)
    try:
        value = client.get(key)
        ttl = client.ttl(key)
        return (str(value) if value else None), int(ttl) if ttl is not None else None
    except Exception as exc:
        logger.warning('[cache] Falha ao consultar chave %s: %s', key, exc)
        return None, None


def set_hash(process_id: int, content_hash: str) -> bool:
    client = _client()
    if client is None:
        return False
    key = _key(process_id)
    ttl = int(getattr(settings, 'PROCESS_HASH_REDIS_TTL_SECONDS', 7200))
    try:
        client.setex(key, ttl, content_hash)
        return True
    except Exception as exc:
        logger.warning('[cache] Falha ao salvar hash em %s: %s', key, exc)
        return False


def renew_ttl_if_needed(process_id: int, ttl_remaining: int | None) -> bool:
    if ttl_remaining is None:
        return False
    renew_threshold = int(getattr(settings, 'PROCESS_HASH_REDIS_RENEW_THRESHOLD_SECONDS', 600))
    if ttl_remaining < 0 or ttl_remaining >= renew_threshold:
        return False

    client = _client()
    if client is None:
        return False

    key = _key(process_id)
    ttl = int(getattr(settings, 'PROCESS_HASH_REDIS_TTL_SECONDS', 7200))
    try:
        return bool(client.expire(key, ttl))
    except Exception as exc:
        logger.warning('[cache] Falha ao renovar TTL da chave %s: %s', key, exc)
        return False

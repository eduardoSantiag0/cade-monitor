"""
Inicialização opcional de rastreamento de erros (Sentry ou serviço compatível).

Ativado apenas quando SENTRY_DSN está definido no ambiente — sem DSN, esta
função não faz nada, e a aplicação continua funcionando normalmente. O
rastreamento de erros é estritamente opcional, nunca uma dependência dura
(spec 002-repo-hardening-cleanup, FR-010).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_sentry(dsn: str, environment: str = 'production') -> bool:
    """Inicializa o SDK de erro se houver DSN configurado. Retorna se ativou."""
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            '[sentry] SENTRY_DSN configurado, mas o pacote sentry-sdk não está instalado.'
        )
        return False

    sentry_sdk.init(dsn=dsn, environment=environment, traces_sample_rate=0.0)
    logger.info('[sentry] Rastreamento de erros ativado (environment=%s).', environment)
    return True

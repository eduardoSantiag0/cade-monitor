"""
Construção de settings.DATABASES a partir das variáveis de ambiente.

Regra de seleção (spec 005-postgres-render):
  - DATABASE_URL ausente → SQLite local (dev/testes), com o mesmo bloco de sempre.
  - DATABASE_URL presente → PostgreSQL (produção no Render).
  - DATABASE_URL vazia/inválida → ImproperlyConfigured na subida.

O parse usa apenas urllib.parse (sem dj-database-url — Princípio VIII).
Mensagens de erro nunca incluem a senha.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from .env_schema import EnvSettings

POSTGRES_SCHEMES = {'postgres', 'postgresql'}
DEFAULT_POSTGRES_PORT = 5432


def _mask_password(url: str) -> str:
    """Retorna a URL com a senha trocada por *** para uso em mensagens."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return '<DATABASE_URL ilegível>'
    # Manipula o netloc como texto: .port/.hostname podem lançar em URLs inválidas.
    userinfo, sep, hostport = parts.netloc.rpartition('@')
    if not sep or ':' not in userinfo:
        return url
    user = userinfo.split(':', 1)[0]
    return parts._replace(netloc=f'{user}:***@{hostport}').geturl()


def database_config_from_url(url: str, *, conn_max_age: int, sslmode: str) -> dict:
    """Converte uma URL postgresql:// no dict de DATABASES['default']."""
    # Aspas coladas junto com a URL (comum em painéis de env vars) são toleradas.
    url = url.strip().strip('"\'').strip()
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ImproperlyConfigured(f'DATABASE_URL inválida: {_mask_password(url)}') from exc

    if parts.scheme not in POSTGRES_SCHEMES:
        # Mostra só o começo do valor (nunca a senha) para diagnosticar erros de colagem.
        preview = url.split('@', 1)[0].split(':', 2)
        preview = ':'.join(preview[:2]) + (':***' if len(preview) > 2 else '')
        raise ImproperlyConfigured(
            f"DATABASE_URL com esquema {parts.scheme!r} não suportado; use postgresql://. "
            f"Valor recebido começa com {preview[:40]!r}. Confira se não ficou o placeholder, "
            "aspas ou o prefixo 'DATABASE_URL=' dentro do valor."
        )

    name = unquote(parts.path.lstrip('/'))
    if not parts.hostname or not name:
        raise ImproperlyConfigured(
            'DATABASE_URL incompleta (host e nome do banco são obrigatórios): '
            f'{_mask_password(url)}'
        )

    query = parse_qs(parts.query)
    url_sslmode = query.get('sslmode', [''])[0].strip().lower()

    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': name,
        'USER': unquote(parts.username or ''),
        'PASSWORD': unquote(parts.password or ''),
        'HOST': parts.hostname,
        'PORT': str(port or DEFAULT_POSTGRES_PORT),
        # Reaproveita conexões entre requests (evita handshake TLS a cada vez)
        # e valida antes de usar — o provedor encerra conexões ociosas.
        'CONN_MAX_AGE': conn_max_age,
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {'sslmode': url_sslmode or sslmode},
    }


def sqlite_config(sqlite_path: str | Path) -> dict:
    """Bloco SQLite usado em dev/testes. WAL e PRAGMAs: ver apps/monitoring/apps.py."""
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': sqlite_path,
        'OPTIONS': {
            # Espera até 20s por um lock antes de lançar OperationalError.
            # Importante para coexistência do worker com o Gunicorn.
            'timeout': 20,
        },
    }


def build_databases(env: 'EnvSettings') -> dict:
    """Retorna o dict completo de settings.DATABASES conforme o ambiente."""
    if env.database_url is None:
        return {'default': sqlite_config(env.sqlite_path)}
    return {
        'default': database_config_from_url(
            env.database_url,
            conn_max_age=env.db_conn_max_age,
            sslmode=env.db_sslmode,
        )
    }

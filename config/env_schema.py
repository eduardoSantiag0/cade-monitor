"""
Validação centralizada das variáveis de ambiente do Django settings.py.

Usa Pydantic para:
  - Coagir tipos (bool/int/float) com mensagens de erro claras em vez de
    ValueError genéricos espalhados pelo settings.py.
  - Documentar em um único lugar todas as variáveis de ambiente aceitas.
  - Falhar rápido (na subida do processo) se uma variável estiver com
    valor inválido, em vez de falhar silenciosamente em runtime.

Não substitui o .env/os.environ — apenas valida o que já é lido de lá.
"""
from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, field_validator


class EnvSettings(BaseModel):
    """Variáveis de ambiente usadas por config/settings.py, já tipadas e validadas."""

    model_config = ConfigDict(frozen=True)

    # Core
    secret_key: str = 'django-insecure-troque-antes-de-colocar-em-producao'
    debug: bool = False
    allowed_hosts: list[str] = ['localhost', '127.0.0.1']

    # Banco de dados
    sqlite_path: str = ''

    # Internacionalização
    app_timezone: str = 'America/Sao_Paulo'

    # E-mail
    smtp_enabled: bool = False
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_tls: bool = True
    smtp_ssl: bool = False
    mail_from: str = 'cade-monitor@example.com'

    # Evolution API (WhatsApp)
    evolution_enabled: bool = False
    evolution_api_base_url: str = ''
    authentication_api_key: str = ''
    evolution_api_key: str = ''
    evolution_instance_name: str = 'cade-monitor'
    evolution_timeout_seconds: int = 15

    # Monitoramento
    check_interval_seconds: int = 1500
    max_processes_per_cycle: int = 20
    request_timeout_seconds: int = 15
    request_retry_attempts: int = 3
    request_retry_backoff_seconds: float = 1.5
    sleep_between_requests_seconds: float = 2.0
    worker_tick_seconds: int = 5
    user_agent: str = 'CadeMonitor/1.0 (monitoramento-publico; contato: configure USER_AGENT no .env)'
    max_snapshots_per_process: int = 100
    max_notification_attempts: int = 3
    document_download_max_bytes: int = 32 * 1024 * 1024
    email_attachment_max_bytes: int = 8 * 1024 * 1024
    whatsapp_attachment_max_bytes: int = 8 * 1024 * 1024
    process_hash_redis_enabled: bool = False
    process_hash_redis_url: str = ''
    process_hash_redis_key_prefix: str = 'cade-monitor:process-hash'
    process_hash_redis_ttl_seconds: int = 7200
    process_hash_redis_renew_threshold_seconds: int = 600
    min_valid_page_text_length: int = 220
    min_valid_page_size_ratio: float = 0.35

    # Logging
    log_level: str = 'INFO'

    @field_validator('allowed_hosts', mode='before')
    @classmethod
    def _split_allowed_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [h.strip() for h in value.split(',') if h.strip()]
        return value

    @field_validator('evolution_api_base_url', mode='after')
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip('/')

    @field_validator('check_interval_seconds', mode='after')
    @classmethod
    def _enforce_minimum_interval(cls, value: int) -> int:
        return max(1500, value)

    @field_validator('log_level', mode='after')
    @classmethod
    def _uppercase_log_level(cls, value: str) -> str:
        return value.upper()

    @classmethod
    def from_env(cls, base_dir=None) -> 'EnvSettings':
        """Lê os valores brutos de os.environ e valida/coage os tipos."""
        default_sqlite_path = str(base_dir / 'data' / 'cade-monitor.sqlite3') if base_dir else ''
        env = os.environ
        raw: dict[str, object] = {}

        def _set(key: str, env_name: str, default: object) -> None:
            if env_name in env:
                raw[key] = env[env_name]
            else:
                raw[key] = default

        _set('secret_key', 'SECRET_KEY', cls.model_fields['secret_key'].default)
        _set('debug', 'DEBUG', cls.model_fields['debug'].default)
        _set('allowed_hosts', 'ALLOWED_HOSTS', 'localhost,127.0.0.1')
        _set('sqlite_path', 'SQLITE_PATH', default_sqlite_path)
        _set('app_timezone', 'APP_TIMEZONE', cls.model_fields['app_timezone'].default)
        _set('smtp_enabled', 'SMTP_ENABLED', cls.model_fields['smtp_enabled'].default)
        _set('smtp_host', 'SMTP_HOST', cls.model_fields['smtp_host'].default)
        _set('smtp_port', 'SMTP_PORT', cls.model_fields['smtp_port'].default)
        _set('smtp_user', 'SMTP_USER', cls.model_fields['smtp_user'].default)
        _set('smtp_password', 'SMTP_PASSWORD', cls.model_fields['smtp_password'].default)
        _set('smtp_tls', 'SMTP_TLS', cls.model_fields['smtp_tls'].default)
        _set('smtp_ssl', 'SMTP_SSL', cls.model_fields['smtp_ssl'].default)
        _set('mail_from', 'MAIL_FROM', env.get('SMTP_USER', cls.model_fields['mail_from'].default))
        _set('evolution_enabled', 'EVOLUTION_ENABLED', cls.model_fields['evolution_enabled'].default)
        _set('evolution_api_base_url', 'EVOLUTION_API_BASE_URL', cls.model_fields['evolution_api_base_url'].default)
        _set('authentication_api_key', 'AUTHENTICATION_API_KEY', cls.model_fields['authentication_api_key'].default)
        _set(
            'evolution_api_key',
            'EVOLUTION_API_KEY',
            env.get('AUTHENTICATION_API_KEY') or cls.model_fields['evolution_api_key'].default,
        )
        _set('evolution_instance_name', 'EVOLUTION_INSTANCE_NAME', cls.model_fields['evolution_instance_name'].default)
        _set('evolution_timeout_seconds', 'EVOLUTION_TIMEOUT_SECONDS', cls.model_fields['evolution_timeout_seconds'].default)
        _set('check_interval_seconds', 'CHECK_INTERVAL_SECONDS', cls.model_fields['check_interval_seconds'].default)
        _set('max_processes_per_cycle', 'MAX_PROCESSES_PER_CYCLE', cls.model_fields['max_processes_per_cycle'].default)
        _set('request_timeout_seconds', 'REQUEST_TIMEOUT_SECONDS', cls.model_fields['request_timeout_seconds'].default)
        _set('request_retry_attempts', 'REQUEST_RETRY_ATTEMPTS', cls.model_fields['request_retry_attempts'].default)
        _set(
            'request_retry_backoff_seconds',
            'REQUEST_RETRY_BACKOFF_SECONDS',
            cls.model_fields['request_retry_backoff_seconds'].default,
        )
        _set(
            'sleep_between_requests_seconds',
            'SLEEP_BETWEEN_REQUESTS_SECONDS',
            cls.model_fields['sleep_between_requests_seconds'].default,
        )
        _set('worker_tick_seconds', 'WORKER_TICK_SECONDS', cls.model_fields['worker_tick_seconds'].default)
        _set('user_agent', 'USER_AGENT', cls.model_fields['user_agent'].default)
        _set('max_snapshots_per_process', 'MAX_SNAPSHOTS_PER_PROCESS', cls.model_fields['max_snapshots_per_process'].default)
        _set('max_notification_attempts', 'MAX_NOTIFICATION_ATTEMPTS', cls.model_fields['max_notification_attempts'].default)
        _set(
            'document_download_max_bytes',
            'DOCUMENT_DOWNLOAD_MAX_BYTES',
            cls.model_fields['document_download_max_bytes'].default,
        )
        _set(
            'email_attachment_max_bytes',
            'EMAIL_ATTACHMENT_MAX_BYTES',
            cls.model_fields['email_attachment_max_bytes'].default,
        )
        _set(
            'whatsapp_attachment_max_bytes',
            'WHATSAPP_ATTACHMENT_MAX_BYTES',
            cls.model_fields['whatsapp_attachment_max_bytes'].default,
        )
        _set(
            'process_hash_redis_enabled',
            'PROCESS_HASH_REDIS_ENABLED',
            cls.model_fields['process_hash_redis_enabled'].default,
        )
        _set('process_hash_redis_url', 'PROCESS_HASH_REDIS_URL', cls.model_fields['process_hash_redis_url'].default)
        _set(
            'process_hash_redis_key_prefix',
            'PROCESS_HASH_REDIS_KEY_PREFIX',
            cls.model_fields['process_hash_redis_key_prefix'].default,
        )
        _set(
            'process_hash_redis_ttl_seconds',
            'PROCESS_HASH_REDIS_TTL_SECONDS',
            cls.model_fields['process_hash_redis_ttl_seconds'].default,
        )
        _set(
            'process_hash_redis_renew_threshold_seconds',
            'PROCESS_HASH_REDIS_RENEW_THRESHOLD_SECONDS',
            cls.model_fields['process_hash_redis_renew_threshold_seconds'].default,
        )
        _set(
            'min_valid_page_text_length',
            'MIN_VALID_PAGE_TEXT_LENGTH',
            cls.model_fields['min_valid_page_text_length'].default,
        )
        _set(
            'min_valid_page_size_ratio',
            'MIN_VALID_PAGE_SIZE_RATIO',
            cls.model_fields['min_valid_page_size_ratio'].default,
        )
        _set('log_level', 'LOG_LEVEL', cls.model_fields['log_level'].default)

        return cls(**raw)

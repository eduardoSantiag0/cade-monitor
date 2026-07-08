
from __future__ import annotations

import os
from dataclasses import dataclass

from .utils import as_bool, as_int


@dataclass(frozen=True)
class Config:
    env_path: str
    db_path: str
    admin_user: str
    admin_password: str
    app_secret_key: str
    poll_interval_minutes: int
    poll_interval_seconds: int
    worker_tick_seconds: int
    request_timeout_seconds: int
    user_agent: str
    base_url: str

    mail_host: str
    mail_port: int
    mail_user: str
    mail_password: str
    mail_from: str
    mail_tls: bool
    mail_ssl: bool

    whatsapp_provider: str
    evolution_enabled: bool
    evolution_api_base_url: str
    evolution_api_key: str
    evolution_instance_name: str
    evolution_timeout_seconds: int

    @classmethod
    def from_env(cls) -> 'Config':
        poll_interval_minutes = max(25, as_int(os.getenv('POLL_INTERVAL_MINUTES'), 25))
        return cls(
            env_path=os.getenv('CADEMON_ENV_PATH', '.env'),
            db_path=os.getenv('DB_PATH', 'data/cade-monitor.sqlite3'),
            admin_user=os.getenv('ADMIN_USER', 'admin'),
            admin_password=os.getenv('ADMIN_PASSWORD', 'troque-esta-senha'),
            app_secret_key=os.getenv('APP_SECRET_KEY', 'troque-esta-chave'),
            poll_interval_minutes=poll_interval_minutes,
            poll_interval_seconds=poll_interval_minutes * 60,
            worker_tick_seconds=max(2, as_int(os.getenv('WORKER_TICK_SECONDS'), 5)),
            request_timeout_seconds=max(5, as_int(os.getenv('REQUEST_TIMEOUT_SECONDS'), 20)),
            user_agent=os.getenv('USER_AGENT', 'Meskade/0.1 contato: configure USER_AGENT no .env'),
            base_url=os.getenv('BASE_URL', ''),
            mail_host=os.getenv('SMTP_HOST', ''),
            mail_port=as_int(os.getenv('SMTP_PORT'), 587),
            mail_user=os.getenv('SMTP_USER', ''),
            mail_password=os.getenv('SMTP_PASSWORD', ''),
            mail_from=os.getenv('MAIL_FROM', os.getenv('SMTP_USER', '')),
            mail_tls=as_bool(os.getenv('SMTP_TLS'), True),
            mail_ssl=as_bool(os.getenv('SMTP_SSL'), False),
            whatsapp_provider=os.getenv('WHATSAPP_PROVIDER', 'evolution').strip().lower(),
            evolution_enabled=as_bool(os.getenv('EVOLUTION_ENABLED'), False),
            evolution_api_base_url=os.getenv('EVOLUTION_API_BASE_URL', '').rstrip('/'),
            evolution_api_key=os.getenv('AUTHENTICATION_API_KEY') or os.getenv('EVOLUTION_API_KEY', ''),
            evolution_instance_name=os.getenv('EVOLUTION_INSTANCE_NAME', 'cade-monitor'),
            evolution_timeout_seconds=max(5, as_int(os.getenv('EVOLUTION_TIMEOUT_SECONDS'), 15)),
        )

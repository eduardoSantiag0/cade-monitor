"""
Configurações centrais do CADE Monitor.

Variáveis sensíveis são lidas do .env (via python-dotenv).
Nunca versione o arquivo .env com valores reais.
"""
from pathlib import Path

from dotenv import load_dotenv

from .database import build_databases
from .env_schema import EnvSettings

BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega .env antes de qualquer leitura de variável
load_dotenv(BASE_DIR / '.env')

# Valida e tipa todas as variáveis de ambiente usadas abaixo. Falha rápido
# (na subida do processo) com uma mensagem clara se algum valor for inválido.
env = EnvSettings.from_env(base_dir=BASE_DIR)

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env.secret_key
DEBUG = env.debug
ALLOWED_HOSTS = env.allowed_hosts

# ---------------------------------------------------------------------------
# Aplicações
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Apps do projeto — paths explícitos para evitar ambiguidade
    'apps.processes.apps.ProcessesConfig',
    'apps.monitoring.apps.MonitoringConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.subscribers.apps.SubscribersConfig',
    'apps.dashboard.apps.DashboardConfig',
    'apps.telegram_bot.apps.TelegramBotConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise serve arquivos estáticos diretamente, sem depender do DEBUG.
    # Deve ficar logo após SecurityMiddleware.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Banco de dados — PostgreSQL via DATABASE_URL (produção); sem ela, SQLite com
# WAL mode para dev/testes (PRAGMAs via signal em monitoring/apps.py).
# ---------------------------------------------------------------------------
SQLITE_PATH = env.sqlite_path

DATABASES = build_databases(env)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/'

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = env.app_timezone
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Arquivos estáticos
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Em produção (DEBUG=False), WhiteNoise comprime e adiciona hash ao nome dos arquivos.
# Em desenvolvimento, usa o storage padrão para não exigir collectstatic a cada alteração.
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------
EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend'
    if env.smtp_enabled
    else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = env.smtp_host
EMAIL_PORT = env.smtp_port
EMAIL_HOST_USER = env.smtp_user
EMAIL_HOST_PASSWORD = env.smtp_password
EMAIL_USE_TLS = env.smtp_tls
EMAIL_USE_SSL = env.smtp_ssl
DEFAULT_FROM_EMAIL = env.mail_from
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------------------
# Evolution API (WhatsApp)
# ---------------------------------------------------------------------------
EVOLUTION_ENABLED = env.evolution_enabled
EVOLUTION_API_BASE_URL = env.evolution_api_base_url
# Evolution aceita chave global (AUTHENTICATION_API_KEY) ou token de instância.
AUTHENTICATION_API_KEY = env.authentication_api_key
EVOLUTION_API_KEY = env.evolution_api_key
EVOLUTION_INSTANCE_NAME = env.evolution_instance_name
EVOLUTION_TIMEOUT_SECONDS = env.evolution_timeout_seconds

# ---------------------------------------------------------------------------
# Telegram (canal principal — webhook em /telegram/webhook/)
# ---------------------------------------------------------------------------
BASE_URL = env.base_url
TELEGRAM_ENABLED = env.telegram_enabled
TELEGRAM_BOT_TOKEN = env.telegram_bot_token
TELEGRAM_WEBHOOK_SECRET = env.telegram_webhook_secret
TELEGRAM_BOT_USERNAME = env.telegram_bot_username
TELEGRAM_MAX_PROCESSES_PER_CHAT = env.telegram_max_processes_per_chat
# Intervalo mínimo entre consultas ao SEI pedidas por /check (e entre retentativas da 1ª leitura).
TELEGRAM_CHECK_COOLDOWN_SECONDS = env.telegram_check_cooldown_seconds
TELEGRAM_HISTORY_LIMIT = env.telegram_history_limit
TELEGRAM_TIMEOUT_SECONDS = env.telegram_timeout_seconds

# ---------------------------------------------------------------------------
# Monitoramento
# ---------------------------------------------------------------------------
# Intervalo mínimo global; cada processo pode ter o seu próprio.
CHECK_INTERVAL_SECONDS = env.check_interval_seconds
MAX_PROCESSES_PER_CYCLE = env.max_processes_per_cycle
REQUEST_TIMEOUT_SECONDS = env.request_timeout_seconds
REQUEST_RETRY_ATTEMPTS = env.request_retry_attempts
REQUEST_RETRY_BACKOFF_SECONDS = env.request_retry_backoff_seconds
SLEEP_BETWEEN_REQUESTS_SECONDS = env.sleep_between_requests_seconds
WORKER_TICK_SECONDS = env.worker_tick_seconds
USER_AGENT = env.user_agent
MAX_SNAPSHOTS_PER_PROCESS = env.max_snapshots_per_process
MAX_NOTIFICATION_ATTEMPTS = env.max_notification_attempts
DOCUMENT_DOWNLOAD_MAX_BYTES = env.document_download_max_bytes
EMAIL_ATTACHMENT_MAX_BYTES = env.email_attachment_max_bytes
WHATSAPP_ATTACHMENT_MAX_BYTES = env.whatsapp_attachment_max_bytes
PROCESS_HASH_REDIS_ENABLED = env.process_hash_redis_enabled
PROCESS_HASH_REDIS_URL = env.process_hash_redis_url
PROCESS_HASH_REDIS_KEY_PREFIX = env.process_hash_redis_key_prefix
# TTL mais longo reduz misses de cache sem gerar tráfego excessivo.
PROCESS_HASH_REDIS_TTL_SECONDS = env.process_hash_redis_ttl_seconds
# Renova com margem para evitar expiração durante períodos ativos.
PROCESS_HASH_REDIS_RENEW_THRESHOLD_SECONDS = env.process_hash_redis_renew_threshold_seconds
MIN_VALID_PAGE_TEXT_LENGTH = env.min_valid_page_text_length
MIN_VALID_PAGE_SIZE_RATIO = env.min_valid_page_size_ratio

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = env.log_level

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] {name}: {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'cade-monitor.log'),
            'maxBytes': 5 * 1024 * 1024,  # 5 MB por arquivo
            'backupCount': 3,
            'formatter': 'verbose',
            'delay': True,  # cria o arquivo só quando houver o primeiro log
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# Segurança (somente em produção)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # O Render (e proxies reversos em geral) termina o HTTPS e repassa HTTP ao
    # container. Sem isto, request.is_secure() é False e o CSRF recusa o login
    # no /admin ("Origin checking failed").
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    CSRF_TRUSTED_ORIGINS = env.csrf_trusted_origins

# ---------------------------------------------------------------------------
# Rastreamento de erros (Sentry ou compatível) — opcional, ativado por SENTRY_DSN
# ---------------------------------------------------------------------------
from .sentry import init_sentry  # noqa: E402

SENTRY_DSN = env.sentry_dsn
SENTRY_ENVIRONMENT = env.sentry_environment
init_sentry(SENTRY_DSN, SENTRY_ENVIRONMENT)

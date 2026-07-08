"""
Configurações centrais do CADE Monitor.

Variáveis sensíveis são lidas do .env (via python-dotenv).
Nunca versione o arquivo .env com valores reais.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega .env antes de qualquer leitura de variável
load_dotenv(BASE_DIR / '.env')

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-troque-antes-de-colocar-em-producao')
DEBUG = os.environ.get('DEBUG', 'false').lower() in ('1', 'true', 'yes')
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

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
# Banco de dados — SQLite com WAL mode (ativado via signal em monitoring/apps.py)
# ---------------------------------------------------------------------------
SQLITE_PATH = os.environ.get('SQLITE_PATH', str(BASE_DIR / 'data' / 'cade-monitor.sqlite3'))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': SQLITE_PATH,
        'OPTIONS': {
            # Espera até 20s por um lock antes de lançar OperationalError.
            # Importante para coexistência do worker com o Gunicorn.
            'timeout': 20,
        },
    }
}

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
TIME_ZONE = os.environ.get('APP_TIMEZONE', 'America/Sao_Paulo')
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
_smtp_enabled = os.environ.get('SMTP_ENABLED', 'false').lower() in ('1', 'true', 'yes')
EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend'
    if _smtp_enabled
    else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('SMTP_HOST', '')
EMAIL_PORT = int(os.environ.get('SMTP_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('SMTP_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('SMTP_TLS', 'true').lower() in ('1', 'true', 'yes')
EMAIL_USE_SSL = os.environ.get('SMTP_SSL', 'false').lower() in ('1', 'true', 'yes')
DEFAULT_FROM_EMAIL = os.environ.get('MAIL_FROM', 'cade-monitor@example.com')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------------------
# Evolution API (WhatsApp)
# ---------------------------------------------------------------------------
EVOLUTION_ENABLED = os.environ.get('EVOLUTION_ENABLED', 'false').lower() in ('1', 'true', 'yes')
EVOLUTION_API_BASE_URL = os.environ.get('EVOLUTION_API_BASE_URL', '').rstrip('/')
# Evolution aceita chave global (AUTHENTICATION_API_KEY) ou token de instância.
AUTHENTICATION_API_KEY = os.environ.get('AUTHENTICATION_API_KEY', '')
EVOLUTION_API_KEY = AUTHENTICATION_API_KEY or os.environ.get('EVOLUTION_API_KEY', '')
EVOLUTION_INSTANCE_NAME = os.environ.get('EVOLUTION_INSTANCE_NAME', 'cade-monitor')
EVOLUTION_TIMEOUT_SECONDS = int(os.environ.get('EVOLUTION_TIMEOUT_SECONDS', '15'))

# ---------------------------------------------------------------------------
# Monitoramento
# ---------------------------------------------------------------------------
# Intervalo mínimo global; cada processo pode ter o seu próprio.
CHECK_INTERVAL_SECONDS = max(1500, int(os.environ.get('CHECK_INTERVAL_SECONDS', '1500')))
MAX_PROCESSES_PER_CYCLE = int(os.environ.get('MAX_PROCESSES_PER_CYCLE', '20'))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get('REQUEST_TIMEOUT_SECONDS', '15'))
SLEEP_BETWEEN_REQUESTS_SECONDS = float(os.environ.get('SLEEP_BETWEEN_REQUESTS_SECONDS', '2'))
WORKER_TICK_SECONDS = int(os.environ.get('WORKER_TICK_SECONDS', '5'))
USER_AGENT = os.environ.get(
    'USER_AGENT',
    'CadeMonitor/1.0 (monitoramento-publico; contato: configure USER_AGENT no .env)',
)
MAX_SNAPSHOTS_PER_PROCESS = int(os.environ.get('MAX_SNAPSHOTS_PER_PROCESS', '100'))
MAX_NOTIFICATION_ATTEMPTS = int(os.environ.get('MAX_NOTIFICATION_ATTEMPTS', '3'))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

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

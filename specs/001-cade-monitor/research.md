# Research: CADE Monitor — Gap Resolutions

**Branch**: `001-cade-monitor` | **Date**: 2026-07-07

All NEEDS CLARIFICATION items from plan.md resolved below. No external research was required — decisions are based on Python stdlib, Django built-ins, and existing project constraints.

---

## Gap 1 — Integration Tests

### Django TestClient for Views

**Decision**: Use `django.test.Client` (built-in) for view integration tests.

**Rationale**: `Client` exercises the full Django request/response cycle — URL routing, middleware (including `@login_required`), view logic, ORM queries, and template rendering — with no additional dependencies. All existing tests already use `django.test.TestCase`; no tooling change needed.

**Coverage plan**:

- Authenticate a test user via `self.client.force_login(user)` where views require it.
- Each view: assert status code, template used (`assertTemplateUsed`), and key context variables present.
- Create views: POST valid data → assert redirect + object in DB; POST invalid data → assert form errors shown.

**Alternatives considered**:

- `pytest-django` with `client` fixture — more ergonomic but adds a dependency. Rejected per Constitution Principle VIII.

### Mocking Notification Channels

**Decision**: `unittest.mock.patch` for Evolution API HTTP; `locmem` email backend for SMTP.

**Rationale**:

- `override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')` captures outgoing email in `django.core.mail.outbox` — zero extra dependencies.
- `@patch('apps.notifications.channels.evolution.requests.post')` isolates HTTP calls for the WhatsApp channel without network access.
- Tests assert `NotificationAttempt.objects.filter(channel='email', status='sent').exists()` and equivalent for WhatsApp, plus failure path: mock raises `requests.RequestException` → assert `status='failed'` + non-empty `error_message`.

**Alternatives considered**:

- `responses` library — cleaner HTTP mocking API but adds a dependency. Rejected.
- `httpretty` — same verdict.

---

## Gap 2 — Segurança

### SSRF Protection

**Decision**: Validate that URL hostname resolves exclusively to public IP addresses, using `ipaddress` + `socket` stdlib. Applied at form validation (`ProcessForm.clean_source`) and defense-in-depth at `_try_resolve_url`.

**Rationale**: OWASP A10 (SSRF) requires that user-supplied URLs are not allowed to reach internal network addresses. The check must resolve DNS rather than only pattern-match, because DNS rebinding can bypass pattern-only checks.

**Implementation**:

```python
import ipaddress
import socket
from urllib.parse import urlparse

_PRIVATE_NETS = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),  # link-local
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),         # ULA
]

def is_ssrf_safe(url: str) -> bool:
    """Return True only if all resolved addresses for the URL are public."""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        addrs = {r[4][0] for r in socket.getaddrinfo(host, None)}
    except OSError:
        return False  # unresolvable host — reject
    for addr_str in addrs:
        ip = ipaddress.ip_address(addr_str)
        if ip.is_loopback or ip.is_link_local or ip.is_private:
            return False
        if any(ip in net for net in _PRIVATE_NETS):
            return False
    return bool(addrs)
```

Place in `apps/processes/services.py` (already imports `urlparse`). Call from:

1. `ProcessForm.clean_source()` — raise `ValidationError('URL aponta para rede interna.')` if unsafe.
2. `_try_resolve_url()` — return `''` early and log `WARNING` if resolved URL is unsafe.

**Alternatives considered**:

- `ssrf-py` library — adds a dependency for ~15 lines of stdlib equivalent. Rejected.
- Pattern-only check (no DNS) — insufficient against DNS rebinding. Rejected.

### Login Rate Limiting

**Decision**: No new pip dependency. Document proxy-level rate limiting in README.

**Rationale**: The panel is intranet-only with a small operator team (spec Assumption). Brute-force attack surface is minimal. Adding `django-axes` or `django-ratelimit` requires constitution justification per Principle VIII. The proportionate response is to document that the operator's reverse proxy (nginx, Caddy, Traefik) or router firewall should rate-limit requests to `/accounts/login/`.

Add a `## Security Notes` section to README with the recommended nginx `limit_req` snippet.

If the panel is ever exposed to the internet, `django-axes` becomes justified — note that in README as the upgrade path.

**Alternatives considered**:

- `django-axes` — full account lockout; justified only for internet-facing deployment. Deferred.
- `django-ratelimit` — simpler; same verdict for intranet use.

### ALLOWED_HOSTS Documentation

**Decision**: No code change needed — `settings.py` already reads from env. Add documentation only.

**Rationale**: `ALLOWED_HOSTS` is already read from `os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')`. The gap is purely documentation: `.env.example` must include a commented production example.

```
# .env.example addition
ALLOWED_HOSTS=monitor.yourdomain.com,yourdomain.com
```

---

## Gap 3 — UX do Painel

### Process List Status Filter

**Decision**: Add optional `status` query parameter to `process_list` view; filter via `ProcessStatus` enum in `get_all_processes`.

**Rationale**: Pure Django — no new dependency. The `selectors.py` function gains a keyword argument; the view passes `request.GET.get('status')` to it; the template renders filter links as plain anchor tags (`?status=active`, `?status=paused`, `?status=error`, no param for "all"). Active filter is highlighted with a CSS class.

**Selector change**:

```python
def get_all_processes(status: str | None = None):
    qs = MonitoredProcess.objects.all()
    if status:
        qs = qs.filter(status=status)
    return qs.order_by('-last_changed_at', '-updated_at')
```

### Change History Pagination

**Decision**: Replace hard `[:20]` slice in `process_detail` view with Django `Paginator(queryset, 20)`. Render standard prev/next controls in template.

**Rationale**: Django's built-in `Paginator` is the standard solution — no JavaScript, no dependency. Keeps server-side rendering consistent with the no-SPA constraint. Page 1 of 20 changes is the default. URL param `?page=N` is standard Django Paginator convention.

**View change**:

```python
from django.core.paginator import Paginator

paginator = Paginator(
    DetectedChange.objects.filter(process=process).order_by('-detected_at'),
    20,
)
page_obj = paginator.get_page(request.GET.get('page'))
context['page_obj'] = page_obj
# remove 'recent_changes' key (or keep as alias for backward compat)
```

---

## Gap 4 — Backup do SQLite

**Decision**: Use `sqlite3.Connection.backup()` (Python 3.7+ built-in) for live-safe copy. Write to timestamped file in `data/backups/`.

**Rationale**: `sqlite3.Connection.backup()` respects WAL mode and active connections — it copies only committed pages and is safe to run while the worker and web server are running. `shutil.copy2` could copy mid-write and produce a corrupt backup.

**Implementation sketch**:

```python
import sqlite3, shutil
from pathlib import Path
from datetime import datetime

def backup_database(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    dest = backup_dir / f'cade-monitor-{ts}.sqlite3'
    src_conn = sqlite3.connect(db_path)
    dst_conn = sqlite3.connect(dest)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()
    return dest
```

**Retention**: After writing, sort existing `cade-monitor-*.sqlite3` files by name (ISO timestamp sorts lexicographically), delete all but the newest `--keep N`.

**Alternatives considered**:

- `VACUUM INTO 'path'` SQL command — atomic but requires SQLite 3.27+ and direct connection; `sqlite3.Connection.backup()` is simpler and available since Python 3.7. Rejected.
- `shutil.copy2` — risk of copying partial WAL state. Rejected for primary backup; acceptable as emergency fallback.

---

## Gap 5 — Cron no Docker Compose

**Decision**: Add `scheduler` service to `docker-compose.yml` using `supercronic` to run management commands on a crontab schedule.

**Rationale**:

- `supercronic` is a single static binary (~6 MB compressed) designed for containers: reads a standard crontab file, runs jobs with proper stdout logging, and exits cleanly on SIGTERM.
- Alternative — shell loop (`while true; do ...; sleep N; done`) — imprecise scheduling, no missed-job tracking, harder to maintain. Rejected.
- Alternative — `celery beat` — violates Constitution Principle I (no task queue). Rejected.
- Alternative — host `crontab` — requires host access; defeats Docker encapsulation. Rejected.

**Dockerfile addition**:

```dockerfile
# Add after main app dependencies
ARG SUPERCRONIC_VERSION=0.2.29
ARG SUPERCRONIC_SHA1=3a8da28f78d8e56fe7aab5c4c83e5b5bbc8b2b33
RUN curl -fsSL https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64 \
    -o /usr/local/bin/supercronic \
    && echo "${SUPERCRONIC_SHA1}  /usr/local/bin/supercronic" | sha1sum -c - \
    && chmod +x /usr/local/bin/supercronic
```

**`scripts/crontab`**:

```
# CADE Monitor — scheduled jobs
# Daily digest — 08:00 every day
0 8 * * *  python manage.py generate_daily_digest

# SQLite backup — 03:00 every day
0 3 * * *  python manage.py backup_db

# Snapshot cleanup — 02:00 every Sunday
0 2 * * 0  python manage.py cleanup_snapshots
```

**`docker-compose.yml` addition**:

```yaml
scheduler:
    build: .
    command: supercronic /app/scripts/crontab
    env_file: .env
    volumes:
        - ./data:/app/data
        - ./logs:/app/logs
    depends_on:
        - web
    restart: unless-stopped
```

The `scheduler` service shares the same Docker image as `web` and `worker`, mounts the same `data/` volume, and restarts automatically.

---

## Gap 6 — Validação de Variáveis de Ambiente

**Decision**: Keep `python-dotenv`; add a `_validate_env()` function at the end of `config/settings.py` to catch critical misconfiguration at startup.

**Rationale**: Replacing `python-dotenv` with `django-environ` would require rewriting every `os.environ.get(...)` call — significant churn for a working codebase with no new capability. Constitution Principle VIII: no unjustified complexity. A small inline validator is proportionate and adds zero dependencies.

**Implementation**:

```python
def _validate_env() -> None:
    from django.core.exceptions import ImproperlyConfigured
    import logging as _logging
    _log = _logging.getLogger(__name__)

    if not DEBUG and SECRET_KEY.startswith('django-insecure-'):
        raise ImproperlyConfigured(
            'SECRET_KEY ainda tem o valor padrão inseguro. '
            'Defina SECRET_KEY no .env antes de rodar em produção.'
        )

    evo_url = os.environ.get('EVOLUTION_API_URL', '')
    evo_key = os.environ.get('EVOLUTION_API_KEY', '')
    if evo_url and not evo_key:
        _log.warning(
            '[settings] EVOLUTION_API_URL está definida mas EVOLUTION_API_KEY está vazia. '
            'Notificações WhatsApp falharão.'
        )

_validate_env()
```

**Alternatives considered**:

- `django-environ` — cleaner typed env API; migration cost unjustified. Deferred to a future amendment if new settings complexity arises.
- `pydantic-settings` — type-safe Pydantic v2 settings model; adds `pydantic` dependency. Rejected per Principle VIII.

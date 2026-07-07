# Implementation Plan: CADE Monitor Platform

**Branch**: `001-cade-monitor` | **Date**: 2026-07-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-cade-monitor/spec.md`

**Status**: Project largely implemented — this plan documents the current state and organizes remaining work across six targeted gaps.

## Summary

CADE Monitor is a Django monolith that periodically scrapes public CADE/SEI process pages, detects content changes via SHA-256 hashing and structured diff, and notifies subscribers by e-mail and WhatsApp (Evolution API). The project is substantially implemented with all domain models, services, scraping pipeline, notification channels, management commands, templates, and Docker infrastructure in place, with 36 passing tests.

This plan acknowledges the completed foundation and focuses remaining phases on six gaps: integration tests for views and notification channels, SSRF-safe URL validation, UX improvements (status filter + change history pagination), a `backup_db` management command, Docker Compose scheduler service for cron jobs, and validated environment variable loading.

---

## Technical Context

**Language/Version**: Python 3.11 / Django 5.x

**Primary Dependencies**: Django 5.x, WhiteNoise, python-dotenv, BeautifulSoup4, requests

**Storage**: SQLite with WAL mode (activated via `connection_created` signal in `MonitoringConfig.ready()`)

**Testing**: Django TestCase (unittest), 36 passing tests across 4 test files (`test_monitoring.py`, `test_notifications.py`, `test_processes.py`, `test_scraper.py`)

**Target Platform**: Linux VM / Docker container — 1–2 vCPU, ≤ 512 MB RAM available to Django process

**Project Type**: Django monolith web application + background worker (management command loop)

**Performance Goals**: Page load < 3 s with ≤ 200 processes (SC-007); worker cycle completing without SQLite lock contention; idle memory < 512 MB (SC-003)

**Constraints**: Single SQLite writer; sequential scraping at minimum 1500 s per process; no external broker; WhatsApp via self-hosted Evolution API only; no SPA framework; no task queues

**Scale/Scope**: Tens of monitored processes; small internal operator team; intranet usage without multi-user authentication in MVP

---

## Constitution Check

_GATE: All principles verified against current implementation and planned gaps._

| Principle                                  | Status     | Notes                                                                                                                  |
| ------------------------------------------ | ---------- | ---------------------------------------------------------------------------------------------------------------------- |
| I. Simplicidade Operacional                | ✅ PASS    | Single Gunicorn worker; `run_worker` management command; no Redis/Celery/RQ                                            |
| II. Monitoramento Responsável              | ✅ PASS    | Min 1500 s interval enforced in `ProcessForm` + model default; sequential scraping; HTTP GET only on public URLs       |
| III. Django Monolítico Bem Organizado      | ✅ PASS    | 5 domain apps; `services.py` / `selectors.py` pattern; thin views                                                      |
| IV. SQLite em Produção                     | ✅ PASS    | WAL mode via `connection_created`; Docker volume for `data/` dir; single sequential writer                             |
| V. Notificações via Evolution API + SMTP   | ✅ PASS    | `notifications/channels/email.py` + `evolution.py`; `NotificationAttempt` recorded per attempt                         |
| VI. Humanização das Mensagens              | ✅ PASS    | PT-BR messages throughout; structured diff (andamentos/protocolos); `ChangeReview` classification statuses             |
| VII. Portfólio-Ready — Qualidade de Código | ⚠️ PARTIAL | 36 unit tests pass; **gap**: no view integration tests; no channel mock tests covering `NotificationAttempt` recording |
| VIII. Sem Over-Engineering                 | ✅ PASS    | All gap fixes use Django built-ins and Python stdlib; no new pip dependencies introduced                               |

**Gate result**: PASS with one partial. Gap 1 (integration tests) resolves the partial on Principle VII. No blockers to proceeding.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-cade-monitor/
├── plan.md                        # This file
├── research.md                    # Phase 0 output — gap research decisions
├── data-model.md                  # Phase 1 output — entity documentation
├── quickstart.md                  # Phase 1 output — validation guide for gaps
├── contracts/
│   ├── url-routes.md              # Phase 1 output — web URL routing contracts
│   └── management-commands.md    # Phase 1 output — CLI command interface contracts
└── tasks.md                       # Phase 2 output — /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
apps/
├── processes/
│   ├── services.py         ⚠️  gap 2 — add SSRF validation in _try_resolve_url / create_process
│   ├── selectors.py        ⚠️  gap 3 — add optional status param to get_all_processes
│   ├── forms.py            ⚠️  gap 2 — add SSRF check in clean_source
│   └── views.py            ⚠️  gap 3 — add status filter passthrough + change history pagination
├── monitoring/
│   └── management/commands/
│       └── backup_db.py    ⬜  gap 4 — new management command (sqlite3.Connection.backup)
├── notifications/          ✅  implemented
├── subscribers/            ✅  implemented
└── dashboard/              ✅  implemented

tests/
├── test_monitoring.py      ✅  36 tests passing (unit)
├── test_notifications.py   ✅  implemented (unit)
├── test_processes.py       ✅  implemented (unit)
├── test_scraper.py         ✅  implemented (unit)
├── test_views.py           ⬜  gap 1 — Django Client integration tests for all views
└── test_channels.py        ⬜  gap 1 — notification channel mock tests

templates/processes/
├── list.html               ⚠️  gap 3 — add status filter links
└── detail.html             ⚠️  gap 3 — add pagination controls for change history

config/
└── settings.py             ⚠️  gap 6 — add _validate_env() for critical settings

docker-compose.yml          ⚠️  gap 5 — add scheduler service with supercronic
scripts/
└── crontab                 ⬜  gap 5 — new crontab file for supercronic scheduler

.env.example                ⚠️  gap 2/6 — document ALLOWED_HOSTS and all required vars
```

---

## Remaining Work: Six Gaps

### Gap 1 — Integration Tests

**Scope**: View tests with Django `Client` + notification channel mock tests.

- `tests/test_views.py`: Cover every view in `processes`, `subscribers`, `dashboard`. Verify HTTP 200 with expected template context; redirect to login for unauthenticated requests; form submission happy path and validation errors.
- `tests/test_channels.py`: Patch `requests.post` for Evolution API channel; use `locmem` email backend for SMTP channel. Assert `NotificationAttempt` is created with correct `channel`, `status`, and `error_message` on both success and failure paths.

**See**: [research.md](research.md#gap-1--integration-tests)

### Gap 2 — Segurança

**Scope**: SSRF protection, login rate limit guidance, ALLOWED_HOSTS documentation.

- Add `is_ssrf_safe(url)` utility in `apps/processes/services.py` using `ipaddress` + `socket` stdlib. Validate in `ProcessForm.clean_source()` and `_try_resolve_url()`.
- Document recommended proxy-level login rate limiting in README (no new pip dependency; intranet risk is low).
- Add `ALLOWED_HOSTS=monitor.yourdomain.com` example to `.env.example`.

**See**: [research.md](research.md#gap-2--segurança)

### Gap 3 — UX do Painel

**Scope**: Process list status filter + change history pagination.

- `get_all_processes(status=None)` gains optional `status` kwarg; `process_list` view passes `request.GET.get('status')`.
- `process_detail` view uses `Paginator(queryset, 20)` replacing hard `[:20]` slice.
- Template updates: filter link row in `list.html`; prev/next nav in `detail.html`.

**See**: [research.md](research.md#gap-3--ux-do-painel)

### Gap 4 — Backup do SQLite

**Scope**: New management command `backup_db`.

- New file: `apps/monitoring/management/commands/backup_db.py`
- Uses `sqlite3.Connection.backup()` for live-safe copy; writes to `data/backups/cade-monitor-<YYYY-MM-DD_HH-MM-SS>.sqlite3`.
- Options: `--dest <dir>` (override backup dir), `--keep <n>` (retain N most recent backups; default 7).
- Logs bytes copied and destination path.

**See**: [research.md](research.md#gap-4--backup-do-sqlite)

### Gap 5 — Cron no Docker Compose

**Scope**: `scheduler` service running periodic management commands.

- Add `scheduler` service to `docker-compose.yml` using same image, command `supercronic /app/scripts/crontab`.
- New `scripts/crontab` file: daily digest at 08:00, backup at 03:00, weekly cleanup on Sunday at 02:00.
- `supercronic` binary added to `Dockerfile` as a build step.

**See**: [research.md](research.md#gap-5--cron-no-docker-compose)

### Gap 6 — Validação de Variáveis de Ambiente

**Scope**: Typed validation of critical env vars without replacing python-dotenv.

- Add `_validate_env()` at end of `config/settings.py`: raises `ImproperlyConfigured` if `SECRET_KEY` is the insecure default in non-DEBUG mode; logs a warning if `EVOLUTION_API_URL` is set but `EVOLUTION_API_KEY` is empty.
- No new dependency; no migration of existing `os.environ.get(...)` calls.

**See**: [research.md](research.md#gap-6--validação-de-variáveis-de-ambiente)

---

## Complexity Tracking

No constitution violations. All gap resolutions use Django built-ins and Python stdlib — no new pip dependencies introduced.

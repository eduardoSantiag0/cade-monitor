---
description: "Task list for CADE Monitor — remaining gap implementations"
---

# Tasks: CADE Monitor

**Input**: Design documents from `/specs/001-cade-monitor/`

**Status**: Project largely implemented — these tasks address 6 remaining gaps documented in plan.md.

**Tests**: Integration test tasks included (Gap 1 from plan.md — explicitly requested).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependency on an incomplete prior task)
- **[Story]**: Which user story this task belongs to (US2, US3, US5, US6)
- Exact file paths included in all task descriptions

---

## Phase 1: Setup

No project initialization needed — project is fully initialized and running. No setup tasks.

---

## Phase 2: Foundational (Shared Prerequisites)

**Purpose**: Shared utility (`is_ssrf_safe`) and environment config used by Phases 3 and 6. Complete before starting US2 tasks.

- [ ] T001 Add `is_ssrf_safe(url: str) -> bool` utility function to `apps/processes/services.py` using `ipaddress` + `socket` stdlib: parse hostname via `urlparse`; resolve via `socket.getaddrinfo`; reject if any resolved IP is loopback, link-local, private (RFC-1918/ULA), or unresolvable; place above `_try_resolve_url`
- [ ] T002 [P] Add `_validate_env()` to `config/settings.py`: raise `ImproperlyConfigured` if `SECRET_KEY` equals the insecure default string when `DEBUG` is False; log `WARNING` if `EVOLUTION_API_URL` is non-empty but `EVOLUTION_API_KEY` is empty; call `_validate_env()` immediately after its definition at end of file
- [ ] T003 [P] Add `ALLOWED_HOSTS=monitor.yourdomain.com,yourdomain.com`, `EVOLUTION_API_KEY=`, and `EVOLUTION_API_URL=https://evolution.yourdomain.com` commented example lines to `.env.example`

**Checkpoint**: `is_ssrf_safe()` is importable from `apps.processes.services`; `_validate_env()` is called on startup; `.env.example` documents all production-required variables.

---

## Phase 3: US2 — Cadastro de Processos / SSRF Protection (Priority: P1)

**Goal**: Prevent operators from registering processes that resolve to internal network addresses.

**Independent Test**:

```bash
python manage.py test tests.test_processes
# Manual: POST /processes/new/ with source=http://192.168.1.1/ — expect form error "URL aponta para rede interna."
# Manual: POST /processes/new/ with source=http://127.0.0.1:8080/ — same rejection.
# Manual: POST /processes/new/ with a public CADE/SEI URL — expect redirect to detail page.
```

- [ ] T004 [P] [US2] Add SSRF check in `ProcessForm.clean_source()` in `apps/processes/forms.py`: after the existing `http`/`https` scheme validation, call `is_ssrf_safe(source)` (imported from `apps.processes.services`); raise `ValidationError('URL aponta para rede interna.')` if it returns `False`; apply only when source is a URL (skip check for bare protocol numbers)
- [ ] T005 [P] [US2] Add SSRF check in `_try_resolve_url()` in `apps/processes/services.py`: after a non-empty `url` is returned by `resolve_process_url`, call `is_ssrf_safe(url)`; if it returns `False`, log `WARNING('[process] URL resolvida aponta para rede interna: %s', url)` and return `''`

**Checkpoint**: US2 SSRF protection active — form rejects internal URLs; protocol-number resolver also rejects internal resolved URLs; existing tests still pass.

---

## Phase 4: US3 — Notificação de Assinantes / Channel Tests (Priority: P2)

**Goal**: Verify notification channels record `NotificationAttempt` correctly on both success and failure paths.

**Independent Test**:

```bash
python manage.py test tests.test_channels --verbosity 2
```

- [ ] T006 [US3] Create `tests/test_channels.py` with four test methods:
    - **Email success**: apply `override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')`; call email channel send; assert `len(mail.outbox) == 1` and `NotificationAttempt.objects.filter(channel='email', status='sent').exists()`
    - **Email failure**: patch `django.core.mail.send_mail` to raise `SMTPException`; assert `NotificationAttempt` has `status='failed'` and non-empty `error_message`
    - **WhatsApp success**: `@patch('apps.notifications.channels.evolution.requests.post')` returning mock 200; assert `NotificationAttempt.objects.filter(channel='whatsapp', status='sent').exists()`
    - **WhatsApp failure**: mock raises `requests.RequestException`; assert `NotificationAttempt` has `status='failed'` and non-empty `error_message`

**Checkpoint**: `python manage.py test tests.test_channels` exits 0 with 4 passing tests.

---

## Phase 5: US5 — Painel Web / UX + View Integration Tests (Priority: P3)

**Goal**: Process list filterable by status via `?status=` query param; change history in detail view paginated at 20 per page; all web views covered by Django Client integration tests.

**Independent Test**:

```bash
python manage.py test tests.test_views --verbosity 2
# Manual: /processes/?status=active shows only active processes with "Ativo" filter highlighted
# Manual: /processes/<pk>/?page=2 returns second page of changes (if process has >20 changes)
```

- [ ] T007 [US5] Add optional `status: str | None = None` parameter to `get_all_processes()` in `apps/processes/selectors.py`: when `status` is non-empty, apply `qs = qs.filter(status=status)` before returning; keep existing `annotate` and `order_by` clauses
- [ ] T008 [US5] Update `process_list` view in `apps/processes/views.py`: pass `status=request.GET.get('status')` to `get_all_processes()`; add `current_status` and `status_choices` (list of `(value, label)` from `ProcessStatus`) to template context
- [ ] T009 [US5] Update `process_detail` view in `apps/processes/views.py`: import `Paginator` from `django.core.paginator`; replace the `[:20]` slice on `DetectedChange` queryset with `Paginator(..., 20).get_page(request.GET.get('page'))`; rename context key from `recent_changes` to `page_obj`
- [ ] T010 [P] [US5] Add status filter link row to `templates/processes/list.html`: render "Todos / Ativo / Pausado / Erro / Arquivado" anchor links as `?status=<value>` and `?` for "Todos"; mark current filter with `aria-current="page"` attribute; uses `current_status` variable from context (set by T008)
- [ ] T011 [P] [US5] Update `templates/processes/detail.html`: change loop from `{% for change in recent_changes %}` to `{% for change in page_obj %}`; add pagination nav block below the loop with `page_obj.has_previous`, `page_obj.previous_page_number`, `page_obj.number`, `page_obj.paginator.num_pages`, `page_obj.has_next`, `page_obj.next_page_number` (uses context from T009)
- [ ] T012 [US5] Create `tests/test_views.py` with Django `Client` integration tests covering:
    - Authenticated GET to `/`, `/processes/`, `/processes/new/`, `/processes/<pk>/`, `/processes/<pk>/edit/`, `/subscribers/`, `/subscribers/new/`, `/subscribers/<pk>/`, `/notifications/` — each returns HTTP 200 and uses correct template (`assertTemplateUsed`)
    - Unauthenticated GET to `/processes/` returns HTTP 302 redirect to `/accounts/login/?next=/processes/`
    - `GET /processes/?status=active` — `context['processes']` queryset contains only active processes
    - `GET /processes/<pk>/` — `context['page_obj']` is present with `paginator.per_page == 20`
    - `POST /processes/new/` with valid public URL and label — HTTP 302 redirect; `MonitoredProcess` created in DB
    - `POST /processes/new/` with `source=http://192.168.1.1/` — HTTP 200 with form error (depends on T004)
    - `POST /subscribers/new/` with valid name and email — HTTP 302 redirect; `Subscriber` created in DB

**Checkpoint**: `python manage.py test tests.test_views` passes; all 36 existing tests unaffected.

---

## Phase 6: US6 — Operações de Manutenção (Priority: P3)

**Goal**: `backup_db` management command for live-safe SQLite copies using `sqlite3.Connection.backup()`; `scheduler` Docker Compose service running supercronic for daily digest, nightly backup, and weekly cleanup.

**Independent Test**:

```bash
python manage.py backup_db --dest /tmp/test-backups --keep 2
ls /tmp/test-backups/   # cade-monitor-<YYYY-MM-DD_HH-MM-SS>.sqlite3 present

docker compose build scheduler
docker compose up scheduler --no-deps -d
docker compose logs scheduler   # supercronic startup log visible
```

- [ ] T013 [US6] Create `apps/monitoring/management/commands/backup_db.py` with `--dest data/backups/` and `--keep 7` options: create destination directory with `Path.mkdir(parents=True, exist_ok=True)`; open source and destination connections via `sqlite3.connect`; run `src_conn.backup(dst_conn)` inside a `with dst_conn:` block; close both connections; after writing, sort `cade-monitor-*.sqlite3` files in destination by name and delete all beyond the newest `--keep N`; log `[backup] Backup criado: <dest_path> (<size_mb> MB)`; exit non-zero on any exception
- [ ] T014 [P] [US6] Add supercronic installation to `Dockerfile`: after the `apt-get install curl` step, add a `RUN` layer that downloads `supercronic-linux-amd64` (pin to a specific release tag, e.g. `v0.2.33`), verifies the SHA-256 checksum against the published `.sha256` file, then moves it to `/usr/local/bin/supercronic` and makes it executable; use a single `RUN` command to keep layer count low
- [ ] T015 [P] [US6] Create `scripts/crontab` with three cron entries:
    ```
    0 8 * * * cd /app && python manage.py generate_daily_digest
    0 3 * * * cd /app && python manage.py backup_db
    0 2 * * 0 cd /app && python manage.py cleanup_snapshots
    ```
- [ ] T016 [US6] Add `scheduler` service to `docker-compose.yml`: same `build`, `env_file`, and `volumes` as the `worker` service; `command: supercronic /app/scripts/crontab`; `restart: unless-stopped`; `depends_on` `web` with `condition: service_healthy`

**Checkpoint**: US6 fully operational — `python manage.py backup_db` works standalone; `docker compose up scheduler` starts and logs cron job output.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T017 Add `## Security Notes` section to `README.md` documenting: nginx `limit_req` snippet for rate-limiting POST requests to `/accounts/login/`; note that `django-axes` is the recommended upgrade path if the panel is ever exposed to the public internet

---

## Dependencies

```
T001 ──► T004   (is_ssrf_safe must exist in services.py before forms.py imports it)
T001 ──► T005   (is_ssrf_safe must exist before _try_resolve_url calls it; same file, sequential)
T007 ──► T008   (selector accepts status param before view passes it)
T008 ──► T010   (view passes current_status/status_choices to context before template uses them)
T009 ──► T011   (view passes page_obj to context before template iterates it)
T013 ──► T016   (backup_db command must exist before scheduler invokes it)
T014 ──► T016   (supercronic in image before compose runs it)
T015 ──► T016   (crontab file must exist before scheduler mounts it)
T004, T005, T008–T011 ──► T012   (integration tests cover final implementation state)
```

## Parallel Execution Examples

**Phase 2 (Foundational)**:

```
Sequential:  T001
Parallel:    T002 + T003   (different files; both independent of T001)
```

**Phase 3 (US2) — after T001 completes**:

```
Parallel:    T004 (forms.py) + T005 (services.py)
```

**Phase 5 (US5)**:

```
Sequential:  T007 → T008 → T010
Sequential:  T007 → T009 → T011
Parallel:    T010 + T011   (different template files, same phase)
Then:        T012   (after T010 and T011 are done)
```

**Phase 6 (US6)**:

```
Parallel:    T013 + T014 + T015   (different files, independent)
Then:        T016   (after T013, T014, T015)
```

## Implementation Strategy

**MVP scope** (highest priority): Phases 2–4 — closes the security gap (SSRF) and adds channel test coverage first.

| Increment | Phases            | Gaps Closed                          | Outcome                         |
| --------- | ----------------- | ------------------------------------ | ------------------------------- |
| 1         | Phase 2 + Phase 3 | Gap 2 (SSRF), Gap 6 (env validation) | Security posture hardened       |
| 2         | Phase 4           | Gap 1a (channel tests)               | US3 notification paths verified |
| 3         | Phase 5           | Gap 3 (UX), Gap 1b (view tests)      | UX improved; all views tested   |
| 4         | Phase 6           | Gap 4 (backup), Gap 5 (cron)         | Operational tooling complete    |
| 5         | Phase 7           | —                                    | README polish                   |

After Increment 4 all 6 gaps are closed. Estimated final test count: 36 (existing) + 4 (test_channels) + 8+ (test_views) = 48+ passing tests.

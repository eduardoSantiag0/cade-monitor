# Quickstart: Validação das Lacunas (Gaps 1–6)

**Branch**: `001-cade-monitor` | **Date**: 2026-07-07

This guide documents how to validate each of the six remaining gaps end-to-end after implementation. It assumes the project is running locally or via Docker Compose.

See [data-model.md](data-model.md) for entity reference and [contracts/](contracts/) for URL and command interfaces.

---

## Prerequisites

```bash
# Local development
cp .env.example .env          # fill SECRET_KEY, DEBUG=true
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# OR via Docker Compose
cp .env.example .env
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

---

## Gap 1 — Integration Tests

**Goal**: Verify that the new integration test files pass with Django's test runner.

```bash
# Run only the new integration test files
python manage.py test tests.test_views tests.test_channels --verbosity 2

# Full suite (must still be 36+ tests passing)
python manage.py test
```

**Expected outcomes**:

- `test_views.py`: All views return HTTP 200 for authenticated requests. Unauthenticated GET to `/processes/` returns HTTP 302 redirect to `/accounts/login/?next=/processes/`.
- `test_channels.py`: Email success path → `len(mail.outbox) == 1` and `NotificationAttempt.status == 'sent'`. WhatsApp failure path (mock raises `RequestException`) → `NotificationAttempt.status == 'failed'` with non-empty `error_message`.
- No regressions in the existing 36 tests.

---

## Gap 2 — Segurança

### 2a. SSRF Protection — Form Validation

```bash
# Start the dev server, then in a browser or httpie:
# Attempt to register a process with an internal URL
curl -s -X POST http://localhost:8000/processes/new/ \
  -d "label=Test&source=http://192.168.1.1/&check_interval_seconds=1800&csrfmiddlewaretoken=..." \
  -b "sessionid=..." | grep "rede interna"
```

**Expected**: Form re-renders with error `"URL aponta para rede interna."` — no `MonitoredProcess` created.

```bash
# Verify localhost is also blocked
curl ... -d "source=http://localhost/internal" ... | grep "rede interna"
```

**Expected**: Same error.

### 2b. SSRF Protection — Public URL Allowed

```bash
# A public CADE/SEI URL must still be accepted
curl ... -d "source=https://sei.cade.gov.br/sei/modulos/pesquisa/..." ...
# Expect: redirect to process detail page (HTTP 302)
```

### 2c. ALLOWED_HOSTS Documentation

```bash
cat .env.example | grep ALLOWED_HOSTS
```

**Expected**: Line present: `# ALLOWED_HOSTS=monitor.yourdomain.com,yourdomain.com`

---

## Gap 3 — UX do Painel

### 3a. Status Filter

1. Create processes with different statuses via admin or management commands.
2. Navigate to `/processes/`.
3. Click the "Ativo" filter link → URL becomes `/processes/?status=active`.
4. Verify only active processes are listed.
5. Click "Todos" → all processes shown again.

**Expected**: Filter links render; correct subset returned per status; URL parameter preserved in browser.

### 3b. Change History Pagination

1. Ensure a process has > 20 `DetectedChange` records (create via shell or test fixtures).
2. Navigate to `/processes/<pk>/`.
3. Scroll to change history section.

**Expected**: 20 changes shown on page 1; "Próximo →" link visible. Clicking it loads page 2 (`?page=2`) with the next 20 changes.

```bash
# Shell setup for pagination test
python manage.py shell -c "
from apps.monitoring.models import DetectedChange
from apps.processes.models import MonitoredProcess
p = MonitoredProcess.objects.first()
for i in range(25):
    DetectedChange.objects.create(process=p, diff_text=f'diff {i}', summary=f'Mudança {i}')
print('Created 25 changes')
"
```

---

## Gap 4 — Backup do SQLite

```bash
# Run backup
python manage.py backup_db

# Verify backup file created
ls -lh data/backups/

# Expected output:
# cade-monitor-2026-07-07_03-00-00.sqlite3   (timestamp varies)

# Verify --keep retention
for i in $(seq 1 10); do python manage.py backup_db; done
ls data/backups/ | wc -l
# Expected: 7 (default --keep 7)

# Verify --keep override
python manage.py backup_db --keep 3
ls data/backups/ | wc -l
# Expected: 3

# Verify --dest override
python manage.py backup_db --dest /tmp/mybackups
ls /tmp/mybackups/
```

**Expected log output** (INFO level):

```
[backup] Backup criado: data/backups/cade-monitor-2026-07-07_03-00-00.sqlite3 (X.X MB)
[backup] Backups retidos: 7. Removidos: 0.
```

---

## Gap 5 — Cron no Docker Compose

```bash
# Start all services including scheduler
docker compose up --build -d

# Verify scheduler service is running
docker compose ps scheduler
# Expected: Up

# Check scheduler logs
docker compose logs scheduler
# Expected: supercronic startup banner + "registered N jobs"

# Manually trigger a command via scheduler service to verify environment
docker compose exec scheduler python manage.py generate_daily_digest --dry-run
# Expected: output with change count or "sem mudanças para notificar"

# Verify supercronic binary in image
docker compose exec scheduler which supercronic
# Expected: /usr/local/bin/supercronic

# Verify crontab is mounted
docker compose exec scheduler cat /app/scripts/crontab
# Expected: 3 cron entries (digest, backup, cleanup)
```

---

## Gap 6 — Validação de Variáveis de Ambiente

### 6a. Insecure SECRET_KEY Rejected in Production

```bash
# Simulate production with default key
DEBUG=false SECRET_KEY=django-insecure-troque-antes-de-colocar-em-producao \
  python manage.py check

# Expected: ImproperlyConfigured error mentioning SECRET_KEY
# Message: "SECRET_KEY ainda tem o valor padrão inseguro..."
```

### 6b. Missing EVOLUTION_API_KEY Warning

```bash
EVOLUTION_API_URL=http://evo.example.com python manage.py check 2>&1 | grep EVOLUTION
# Expected: WARNING log:
# "[settings] EVOLUTION_API_URL está definida mas EVOLUTION_API_KEY está vazia."
```

### 6c. Valid Production Config — No Errors

```bash
DEBUG=false SECRET_KEY=supersecretkey123abc ALLOWED_HOSTS=localhost \
  python manage.py check
# Expected: "System check identified no issues (0 silenced)."
```

---

## Full Regression Check

After all gaps are implemented, run the complete test suite:

```bash
python manage.py test --verbosity 2 2>&1 | tail -5
# Expected: "Ran N tests in X.XXXs" with "OK" — zero failures
```

And verify the Django system check passes:

```bash
python manage.py check
# Expected: "System check identified no issues (0 silenced)."
```

# Contract: Management Commands

**Branch**: `001-cade-monitor` | **Date**: 2026-07-07

All commands are invoked via `python manage.py <command>`. All commands have `--help` output per FR-028 and Constitution Principle VII.

---

## Implemented Commands

### `run_worker`

Starts the continuous monitoring loop. Runs indefinitely until interrupted.

```
python manage.py run_worker [--sleep SECONDS]
```

| Option    | Default | Description                                                       |
| --------- | ------- | ----------------------------------------------------------------- |
| `--sleep` | 30      | Sleep interval (seconds) between cycles when no processes are due |

**Behavior**: Queries all active processes whose `last_checked_at + check_interval_seconds ≤ now`, processes them sequentially, then sleeps. Restarts cleanly after container restart (SC-004).

---

### `check_processes`

Single-pass check of all due processes. Non-daemon; exits after one pass. Useful for testing or one-off runs.

```
python manage.py check_processes [--dry-run]
```

| Option      | Default | Description                               |
| ----------- | ------- | ----------------------------------------- |
| `--dry-run` | False   | Fetch and diff but do not persist changes |

---

### `check_process`

Check a single process by PK.

```
python manage.py check_process <process_pk> [--dry-run]
```

---

### `probe_process`

Fetch and extract text from a process URL without creating any database records. Useful for debugging scraping.

```
python manage.py probe_process <process_pk_or_url>
```

---

### `resolve_process`

Re-resolve the URL for a process registered by protocol number.

```
python manage.py resolve_process <process_pk>
```

---

### `send_pending_notifications`

Send all pending (unsent) notifications for detected changes.

```
python manage.py send_pending_notifications [--dry-run]
```

---

### `generate_daily_digest`

Consolidate all changes detected in the last 24 hours and send digest notifications to subscribed users.

```
python manage.py generate_daily_digest [--since HOURS] [--dry-run]
```

| Option      | Default | Description                          |
| ----------- | ------- | ------------------------------------ |
| `--since`   | 24      | Look back N hours for changes        |
| `--dry-run` | False   | Print digest content without sending |

**Acceptance scenario** (US-6 SC-1): exits cleanly with log `"sem mudanças para notificar"` when no changes in the window.

---

### `cleanup_snapshots`

Delete page snapshots older than the configured retention period.

```
python manage.py cleanup_snapshots [--days DAYS] [--dry-run]
```

| Option      | Default                                                | Description                              |
| ----------- | ------------------------------------------------------ | ---------------------------------------- |
| `--days`    | from `AppSetting.snapshot_retention_days` (default 30) | Retention window                         |
| `--dry-run` | False                                                  | Count records to delete without deleting |

Logs the number of deleted records (SC-008).

---

## Gap 4 — New Command: `backup_db`

Copies the SQLite database to a timestamped backup file.

```
python manage.py backup_db [--dest DIR] [--keep N]
```

| Option   | Default         | Description                                                     |
| -------- | --------------- | --------------------------------------------------------------- |
| `--dest` | `data/backups/` | Backup destination directory                                    |
| `--keep` | 7               | Number of most-recent backups to retain; older ones are deleted |

**Output**: Logs `[backup] Backup criado: data/backups/cade-monitor-2026-07-07_03-00-00.sqlite3 (12.4 MB)`.

**Implementation**: `sqlite3.Connection.backup()` — live-safe; respects WAL mode. Does not require stopping the worker or web server.

**Exit codes**: 0 on success; non-zero on failure (e.g., destination not writable).

---

## Scheduled Invocations (Gap 5 — Crontab)

The `scheduler` Docker Compose service runs these on the following schedule:

| Schedule    | Command                 | Purpose                                 |
| ----------- | ----------------------- | --------------------------------------- |
| `0 8 * * *` | `generate_daily_digest` | Daily summary to all active subscribers |
| `0 3 * * *` | `backup_db`             | Nightly database backup                 |
| `0 2 * * 0` | `cleanup_snapshots`     | Weekly snapshot pruning (Sunday 02:00)  |

See [../research.md#gap-5--cron-no-docker-compose](../research.md#gap-5--cron-no-docker-compose) for the supercronic decision.

---

## Environment Requirements

All commands inherit Django settings from `config/settings.py`. The following environment variables must be set for full functionality:

| Variable                  | Required By            | Notes                                                |
| ------------------------- | ---------------------- | ---------------------------------------------------- |
| `SECRET_KEY`              | All                    | Must not be the insecure default in production       |
| `DATABASE_URL` or default | All                    | SQLite path; defaults to `data/cade-monitor.sqlite3` |
| `EVOLUTION_API_URL`       | WhatsApp notifications |                                                      |
| `EVOLUTION_API_KEY`       | WhatsApp notifications | Warning logged if URL set but key missing (Gap 6)    |
| `EMAIL_HOST`              | Email notifications    |                                                      |
| `DEFAULT_FROM_EMAIL`      | Email notifications    |                                                      |

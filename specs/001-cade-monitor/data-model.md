# Data Model: CADE Monitor

**Branch**: `001-cade-monitor` | **Date**: 2026-07-07

All entities are fully implemented. This document serves as the canonical reference for the data model.

---

## Entity Map

```
MonitoredProcess ──< CheckRun ──< PageSnapshot
                 |            └──< DetectedChange >─── Notification ──< NotificationAttempt
                 └──< ProcessSubscription >── Subscriber
```

---

## Entities

### MonitoredProcess

**App**: `processes` | **Table**: `processes_monitoredprocess`

Represents a public CADE/SEI page under monitoring.

| Field                    | Type             | Constraints            | Description                             |
| ------------------------ | ---------------- | ---------------------- | --------------------------------------- |
| `id`                     | integer          | PK, auto               |                                         |
| `label`                  | varchar(300)     | required               | Human-readable name (e.g. "Fusão XYZ")  |
| `source`                 | varchar(1000)    | unique, required       | Raw input: URL or protocol number       |
| `resolved_url`           | URLField(1000)   | optional               | Filled when source is a protocol number |
| `status`                 | varchar(20)      | `ProcessStatus` enum   | `active`, `paused`, `error`, `archived` |
| `check_interval_seconds` | positive integer | default 1500, min 1500 | Polling cadence in seconds              |
| `last_hash`              | varchar(64)      | optional               | SHA-256 of last seen content            |
| `last_text`              | TextField        | optional               | Normalized text of last snapshot        |
| `last_checked_at`        | datetime         | nullable               | Timestamp of last `CheckRun`            |
| `last_changed_at`        | datetime         | nullable               | Timestamp of last detected change       |
| `last_error`             | TextField        | optional               | Most recent error message               |
| `notes`                  | TextField        | optional               | Internal operator notes                 |
| `created_at`             | datetime         | auto                   |                                         |
| `updated_at`             | datetime         | auto                   |                                         |

**Property** `effective_url`: returns `resolved_url` if set, otherwise `source`.

**Validation**: `check_interval_seconds >= 1500` enforced in `ProcessForm.clean_check_interval_seconds`.

**SSRF constraint** (Gap 2): `effective_url` must resolve to a public IP — enforced at form save and at `_try_resolve_url`.

**Indexes**: `(status, last_checked_at)`, `(-last_changed_at, -updated_at)`.

---

### CheckRun

**App**: `monitoring` | **Table**: `monitoring_checkrun`

Audit log of every monitoring cycle execution.

| Field           | Type                  | Constraints        | Description                                            |
| --------------- | --------------------- | ------------------ | ------------------------------------------------------ |
| `id`            | integer               | PK, auto           |                                                        |
| `process`       | FK → MonitoredProcess | CASCADE            |                                                        |
| `status`        | varchar(20)           | `CheckStatus` enum | `started`, `success`, `no_change`, `changed`, `failed` |
| `started_at`    | datetime              | auto               |                                                        |
| `finished_at`   | datetime              | nullable           | Set on completion                                      |
| `error_message` | TextField             | optional           | Populated on `failed` status                           |

**Index**: `(process, -started_at)`.

---

### PageSnapshot

**App**: `monitoring` | **Table**: `monitoring_pagesnapshot`

Stores the normalized text content of a scraped page at a point in time. HTML is not stored.

| Field          | Type                  | Constraints        | Description                         |
| -------------- | --------------------- | ------------------ | ----------------------------------- |
| `id`           | integer               | PK, auto           |                                     |
| `process`      | FK → MonitoredProcess | CASCADE            |                                     |
| `check_run`    | FK → CheckRun         | SET NULL, nullable | The run that produced this snapshot |
| `content_hash` | varchar(64)           | indexed            | SHA-256 of `text_content`           |
| `text_content` | TextField             | required           | Normalized visible text             |
| `fetched_at`   | datetime              | auto               |                                     |

**Index**: `(process, -fetched_at)`.

**Cleanup**: `cleanup_snapshots` management command deletes snapshots older than the retention period configured in `AppSetting`.

---

### DetectedChange

**App**: `monitoring` | **Table**: `monitoring_detectedchange`

Records a confirmed content change between two consecutive snapshots.

| Field             | Type                  | Constraints                       | Description                              |
| ----------------- | --------------------- | --------------------------------- | ---------------------------------------- |
| `id`              | integer               | PK, auto                          |                                          |
| `process`         | FK → MonitoredProcess | CASCADE                           |                                          |
| `check_run`       | FK → CheckRun         | SET NULL, nullable                |                                          |
| `old_snapshot`    | FK → PageSnapshot     | SET NULL, nullable                | Snapshot before change                   |
| `new_snapshot`    | FK → PageSnapshot     | SET NULL, nullable                | Snapshot after change                    |
| `diff_text`       | TextField             | required                          | Full unified diff                        |
| `diff_structured` | JSONField             | optional                          | Structured diff of andamentos/protocolos |
| `summary`         | TextField             | required                          | Human-readable PT-BR change summary      |
| `review`          | varchar(20)           | `ChangeReview` enum, default `''` | Classification by operator               |
| `detected_at`     | datetime              | auto, indexed                     |                                          |

**ChangeReview values**: `''` (unreviewed), `analyzed`, `ignored`, `important`, `false_positive`.

**Index**: `(process, -detected_at)`.

---

### Subscriber

**App**: `subscribers` | **Table**: `subscribers_subscriber`

A person who receives notifications about monitored processes.

| Field              | Type         | Constraints  | Description                        |
| ------------------ | ------------ | ------------ | ---------------------------------- |
| `id`               | integer      | PK, auto     |                                    |
| `name`             | varchar(200) | required     |                                    |
| `email`            | EmailField   | optional     | Used for email notifications       |
| `whatsapp`         | varchar(30)  | optional     | E.164 number for Evolution API     |
| `email_enabled`    | boolean      | default True | Whether email channel is active    |
| `whatsapp_enabled` | boolean      | default True | Whether WhatsApp channel is active |
| `created_at`       | datetime     | auto         |                                    |
| `updated_at`       | datetime     | auto         |                                    |

---

### ProcessSubscription

**App**: `subscribers` | **Table**: `subscribers_processsubscription`

Many-to-many link between Subscriber and MonitoredProcess.

| Field        | Type                  | Constraints  | Description                         |
| ------------ | --------------------- | ------------ | ----------------------------------- |
| `id`         | integer               | PK, auto     |                                     |
| `process`    | FK → MonitoredProcess | CASCADE      |                                     |
| `subscriber` | FK → Subscriber       | CASCADE      |                                     |
| `active`     | boolean               | default True | Can be deactivated per-subscription |
| `created_at` | datetime              | auto         |                                     |

**Unique constraint**: `(process, subscriber)`.

---

### Notification

**App**: `notifications` | **Table**: `notifications_notification`

Groups notification attempts triggered by a single `DetectedChange`.

| Field        | Type                | Constraints | Description |
| ------------ | ------------------- | ----------- | ----------- |
| `id`         | integer             | PK, auto    |             |
| `change`     | FK → DetectedChange | CASCADE     |             |
| `created_at` | datetime            | auto        |             |

---

### NotificationAttempt

**App**: `notifications` | **Table**: `notifications_notificationattempt`

Individual delivery attempt per channel per subscriber.

| Field           | Type              | Constraints                 | Description           |
| --------------- | ----------------- | --------------------------- | --------------------- |
| `id`            | integer           | PK, auto                    |                       |
| `notification`  | FK → Notification | CASCADE                     |                       |
| `subscriber`    | FK → Subscriber   | CASCADE                     |                       |
| `channel`       | varchar(20)       | `email` or `whatsapp`       |                       |
| `status`        | varchar(20)       | `sent`, `failed`, `skipped` |                       |
| `error_message` | TextField         | optional                    | Populated on `failed` |
| `attempted_at`  | datetime          | auto                        |                       |

---

### AppSetting

**App**: `monitoring` (or global settings app) | **Table**: `monitoring_appsetting`

Key-value store for runtime-configurable settings.

| Field   | Type                 | Description                                  |
| ------- | -------------------- | -------------------------------------------- |
| `key`   | varchar(100), unique | Setting key (e.g. `snapshot_retention_days`) |
| `value` | TextField            | String value; cast by consuming code         |

**Known keys**:

- `snapshot_retention_days` — integer; default 30. Used by `cleanup_snapshots`.
- `default_check_interval_seconds` — integer; default 1800. Used by `create_process`.

---

## State Transitions

### MonitoredProcess.status

```
active ──(operator pauses)──> paused
active ──(scrape fails repeatedly)──> error
active/paused/error ──(operator archives)──> archived
paused/error ──(operator reactivates)──> active
```

### DetectedChange.review

```
'' (unreviewed)
  ──(operator reviews)──> analyzed
  ──(operator marks important)──> important
  ──(operator marks noise)──> ignored
  ──(operator confirms false positive)──> false_positive
```

Classification is not reversible by the system; operators can reclassify manually.

---

## Retention Policy

- **PageSnapshot**: deleted by `cleanup_snapshots` when `fetched_at < now - snapshot_retention_days days`. The `DetectedChange` FK uses `SET NULL` to preserve change records after snapshot deletion.
- **CheckRun**: no automatic cleanup (serves as permanent audit log). Consider periodic pruning after 90 days if storage becomes a concern (not in scope for this plan).
- **NotificationAttempt**: permanent record for auditability (SC-005).

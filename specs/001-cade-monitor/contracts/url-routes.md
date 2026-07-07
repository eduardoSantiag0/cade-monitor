# Contract: URL Routes

**Branch**: `001-cade-monitor` | **Date**: 2026-07-07

All routes are fully implemented. This document is the canonical reference.

---

## Route Table

| Method   | Path                      | View                                    | Auth Required | Description                                                              |
| -------- | ------------------------- | --------------------------------------- | ------------- | ------------------------------------------------------------------------ |
| GET      | `/`                       | `dashboard.views.index`                 | Yes           | Main dashboard with metrics                                              |
| GET      | `/processes/`             | `processes.views.process_list`          | Yes           | Paginated list of monitored processes; accepts `?status=` filter (Gap 3) |
| GET      | `/processes/new/`         | `processes.views.process_create`        | Yes           | Create process form                                                      |
| POST     | `/processes/new/`         | `processes.views.process_create`        | Yes           | Submit create process form                                               |
| GET      | `/processes/<pk>/`        | `processes.views.process_detail`        | Yes           | Process detail with change history (paginated, Gap 3) and check runs     |
| GET      | `/processes/<pk>/edit/`   | `processes.views.process_edit`          | Yes           | Edit process form                                                        |
| POST     | `/processes/<pk>/edit/`   | `processes.views.process_edit`          | Yes           | Submit edit form                                                         |
| POST     | `/processes/<pk>/toggle/` | `processes.views.process_toggle_status` | Yes           | Toggle active/paused status (HTMX-friendly redirect)                     |
| GET      | `/subscribers/`           | `subscribers.views.subscriber_list`     | Yes           | List all subscribers                                                     |
| GET      | `/subscribers/new/`       | `subscribers.views.subscriber_create`   | Yes           | Create subscriber form                                                   |
| POST     | `/subscribers/new/`       | `subscribers.views.subscriber_create`   | Yes           | Submit create subscriber                                                 |
| GET      | `/subscribers/<pk>/`      | `subscribers.views.subscriber_detail`   | Yes           | Subscriber detail with subscriptions                                     |
| GET      | `/subscribers/<pk>/edit/` | `subscribers.views.subscriber_edit`     | Yes           | Edit subscriber form                                                     |
| POST     | `/subscribers/<pk>/edit/` | `subscribers.views.subscriber_edit`     | Yes           | Submit edit form                                                         |
| GET      | `/notifications/`         | `notifications.views.notification_list` | Yes           | Notification attempt history                                             |
| GET      | `/accounts/login/`        | `django.contrib.auth.views.LoginView`   | No            | Django built-in login                                                    |
| POST     | `/accounts/login/`        | `django.contrib.auth.views.LoginView`   | No            | Submit credentials                                                       |
| GET/POST | `/accounts/logout/`       | `django.contrib.auth.views.LogoutView`  | Yes           | Log out                                                                  |
| GET      | `/admin/`                 | Django Admin                            | Superuser     | Full ORM access for power users                                          |

---

## URL Namespaces

| Namespace       | App                  | Prefix            |
| --------------- | -------------------- | ----------------- |
| `processes`     | `apps.processes`     | `/processes/`     |
| `subscribers`   | `apps.subscribers`   | `/subscribers/`   |
| `notifications` | `apps.notifications` | `/notifications/` |
| `dashboard`     | `apps.dashboard`     | `/`               |

---

## Query Parameters

### `/processes/` — Status Filter (Gap 3)

| Parameter | Values                                  | Behavior                                       |
| --------- | --------------------------------------- | ---------------------------------------------- |
| `status`  | `active`, `paused`, `error`, `archived` | Filters list to matching status. Omit for all. |

Renders active/paused/error/archived filter links in the template header row. Current filter highlighted with `aria-current="page"` and a CSS `active` class.

### `/processes/<pk>/` — Change History Pagination (Gap 3)

| Parameter | Values      | Behavior                                                       |
| --------- | ----------- | -------------------------------------------------------------- |
| `page`    | integer ≥ 1 | Page of `DetectedChange` history (20 per page). Defaults to 1. |

---

## Authentication

All views except the login/logout endpoints require an authenticated Django session (`@login_required`). Unauthenticated requests are redirected to `/accounts/login/?next=<original-path>`.

The application is designed for intranet use; multi-user permissions beyond "logged in / not logged in" are out of scope for MVP.

---

## Static Files

Static files are served by WhiteNoise middleware directly from Django — no separate Nginx needed for static in development or Docker deployments. Served under `/static/`.

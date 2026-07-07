from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from . import db
from .config import Config
from .notifiers import movement_body, movement_subject, send_email, send_whatsapp
from .scraper import FetchError, collect_new_document_attachments, diff_summary, fetch_snapshot
from .utils import parse_iso


def is_due(row, default_interval: int) -> bool:
    last_checked = parse_iso(row['last_checked_at'])
    if last_checked is None:
        return True
    try:
        interval = int(row['check_interval_seconds'] or default_interval)
    except (TypeError, ValueError):
        interval = default_interval
    interval = max(db.MIN_CHECK_INTERVAL_SECONDS, interval)
    return datetime.now(timezone.utc) >= last_checked + timedelta(seconds=interval)


def check_process(conn, cfg: Config, process_id: int, notify_initial: bool = False) -> dict:
    process = db.get_process(conn, process_id)
    if process is None:
        return {'ok': False, 'changed': False, 'message': 'Processo nao encontrado'}
    try:
        snapshot = fetch_snapshot(process['public_url'], cfg.request_timeout_seconds, cfg.user_agent)
    except FetchError as exc:
        db.record_error(conn, process_id, str(exc))
        return {'ok': False, 'changed': False, 'message': str(exc)}

    old_hash = process['last_hash']
    if not old_hash:
        summary = 'Primeira leitura gravada como linha de base.'
        if notify_initial:
            movement_id = db.record_movement(
                conn,
                process_id,
                None,
                snapshot.hash,
                snapshot.text,
                summary,
                snapshot.text[:8000],
            )
            notify_movement(conn, cfg, process_id, movement_id, summary, snapshot.text[:8000], [])
            return {'ok': True, 'changed': True, 'message': summary}
        db.update_baseline(conn, process_id, snapshot.hash, snapshot.text)
        return {'ok': True, 'changed': False, 'message': summary}

    if snapshot.hash == old_hash:
        db.update_no_change(conn, process_id)
        return {'ok': True, 'changed': False, 'message': 'Sem mudanca detectada.'}

    summary, diff = diff_summary(process['last_text'], snapshot.text)
    attachments, document_errors = collect_new_document_attachments(
        process['last_text'],
        snapshot,
        cfg.request_timeout_seconds,
        cfg.user_agent,
    )
    if attachments or document_errors:
        document_lines: list[str] = []
        if attachments:
            document_lines.append('Documentos baixados para este alerta:')
            document_lines.extend(f"- {item.get('filename')} ({item.get('url')})" for item in attachments)
        if document_errors:
            if document_lines:
                document_lines.append('')
            document_lines.append('Documentos nao anexados:')
            document_lines.extend(f'- {error}' for error in document_errors)
        diff = (diff + '\n\n' + '\n'.join(document_lines))[:8000]

    movement_id = db.record_movement(conn, process_id, old_hash, snapshot.hash, snapshot.text, summary, diff)
    notify_movement(conn, cfg, process_id, movement_id, summary, diff, attachments)
    return {'ok': True, 'changed': True, 'message': summary}


def notify_movement(
    conn,
    cfg: Config,
    process_id: int,
    movement_id: int,
    summary: str,
    diff: str,
    attachments: list[dict[str, object]] | None = None,
) -> None:
    process = db.get_process(conn, process_id)
    if process is None:
        return
    subject = movement_subject(process['label'])
    body = movement_body(process['label'], process['public_url'], summary, diff)
    for subscriber in db.enabled_subscribers(conn, process_id):
        if subscriber['channel'] == 'email':
            status, error = send_email(cfg, subscriber['destination'], subject, body, attachments)
        elif subscriber['channel'] == 'whatsapp':
            status, error = send_whatsapp(cfg, subscriber['destination'], body, attachments)
        else:
            status, error = 'failed', 'Canal desconhecido'
        db.record_notification(
            conn,
            movement_id,
            subscriber['id'],
            subscriber['channel'],
            subscriber['destination'],
            status,
            error,
        )


def check_due_processes(conn, cfg: Config) -> list[dict]:
    results: list[dict] = []
    for process in db.due_processes(conn):
        if not is_due(process, cfg.poll_interval_seconds):
            continue
        result = check_process(conn, cfg, process['id'])
        result['process_id'] = process['id']
        result['label'] = process['label']
        results.append(result)
    return results


def run_worker(cfg: Config) -> None:
    conn = db.connect(cfg.db_path)
    print('Meskade worker iniciado.', flush=True)
    try:
        while True:
            for result in check_due_processes(conn, cfg):
                status = 'mudou' if result.get('changed') else 'ok'
                print(f"[{status}] #{result.get('process_id')} {result.get('label')}: {result.get('message')}", flush=True)
            time.sleep(cfg.worker_tick_seconds)
    except KeyboardInterrupt:
        print('Meskade worker encerrado.', flush=True)
    finally:
        conn.close()

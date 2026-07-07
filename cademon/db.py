
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from .utils import utcnow_iso, validate_public_url


MIN_CHECK_INTERVAL_SECONDS = 25 * 60


SCHEMA = r'''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    public_url TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    check_interval_seconds INTEGER NOT NULL DEFAULT 1500,
    last_hash TEXT,
    last_text TEXT,
    last_checked_at TEXT,
    last_changed_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'whatsapp')),
    destination TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(process_id, channel, destination)
);

CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    detected_at TEXT NOT NULL,
    old_hash TEXT,
    new_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    diff TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_id INTEGER NOT NULL REFERENCES movements(id) ON DELETE CASCADE,
    subscriber_id INTEGER REFERENCES subscribers(id) ON DELETE SET NULL,
    channel TEXT NOT NULL,
    destination TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processes_enabled ON processes(enabled);
CREATE INDEX IF NOT EXISTS idx_subscribers_process ON subscribers(process_id, enabled);
CREATE INDEX IF NOT EXISTS idx_movements_process ON movements(process_id, detected_at DESC);
'''


def local_today() -> str:
    timezone_name = os.getenv('APP_TIMEZONE', 'America/Sao_Paulo')
    try:
        return datetime.now(ZoneInfo(timezone_name)).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def reset_daily_movements(conn: sqlite3.Connection) -> bool:
    state_key = 'last_movements_reset_date'
    today = local_today()
    row = conn.execute('SELECT value FROM app_state WHERE key = ?', (state_key,)).fetchone()
    if row is None:
        conn.execute('INSERT INTO app_state(key, value) VALUES (?, ?)', (state_key, today))
        conn.commit()
        return False
    if row['value'] == today:
        return False
    conn.execute('DELETE FROM notifications')
    conn.execute('DELETE FROM movements')
    conn.execute('UPDATE app_state SET value = ? WHERE key = ?', (today, state_key))
    conn.commit()
    return True


def connect(db_path: str) -> sqlite3.Connection:
    parent = Path(db_path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.executescript(SCHEMA)
    reset_daily_movements(conn)
    return conn


def add_process(
    conn: sqlite3.Connection,
    label: str,
    public_url: str,
    emails: Iterable[str],
    phones: Iterable[str],
    interval_seconds: int,
) -> int:
    now = utcnow_iso()
    clean_url = validate_public_url(public_url)
    clean_label = label.strip() or clean_url
    cur = conn.execute(
        '''
        INSERT INTO processes(label, public_url, check_interval_seconds, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (clean_label, clean_url, max(MIN_CHECK_INTERVAL_SECONDS, int(interval_seconds)), now, now),
    )
    process_id = int(cur.lastrowid)
    for email in emails:
        add_subscriber(conn, process_id, 'email', email)
    for phone in phones:
        add_subscriber(conn, process_id, 'whatsapp', phone)
    conn.commit()
    return process_id


def add_subscriber(conn: sqlite3.Connection, process_id: int, channel: str, destination: str) -> None:
    destination = destination.strip()
    if not destination:
        return
    now = utcnow_iso()
    conn.execute(
        '''
        INSERT OR IGNORE INTO subscribers(process_id, channel, destination, enabled, created_at)
        VALUES (?, ?, ?, 1, ?)
        ''',
        (process_id, channel, destination, now),
    )


def delete_subscriber(conn: sqlite3.Connection, subscriber_id: int) -> None:
    conn.execute('DELETE FROM subscribers WHERE id = ?', (subscriber_id,))
    conn.commit()


def delete_process(conn: sqlite3.Connection, process_id: int) -> None:
    conn.execute('DELETE FROM processes WHERE id = ?', (process_id,))
    conn.commit()


def toggle_process(conn: sqlite3.Connection, process_id: int) -> None:
    conn.execute(
        'UPDATE processes SET enabled = CASE enabled WHEN 1 THEN 0 ELSE 1 END, updated_at = ? WHERE id = ?',
        (utcnow_iso(), process_id),
    )
    conn.commit()


def list_processes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        '''
        SELECT p.*,
               (SELECT COUNT(*) FROM subscribers s WHERE s.process_id = p.id AND s.enabled = 1) AS subscriber_count,
               (SELECT COUNT(*) FROM movements m WHERE m.process_id = p.id) AS movement_count
          FROM processes p
         ORDER BY
               CASE WHEN p.last_changed_at IS NULL THEN 1 ELSE 0 END,
               p.last_changed_at DESC,
               p.updated_at DESC,
               p.id DESC
        '''
    ).fetchall()


def get_process(conn: sqlite3.Connection, process_id: int) -> sqlite3.Row | None:
    return conn.execute('SELECT * FROM processes WHERE id = ?', (process_id,)).fetchone()


def get_subscribers(conn: sqlite3.Connection, process_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        'SELECT * FROM subscribers WHERE process_id = ? ORDER BY channel, destination',
        (process_id,),
    ).fetchall()


def enabled_subscribers(conn: sqlite3.Connection, process_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        'SELECT * FROM subscribers WHERE process_id = ? AND enabled = 1 ORDER BY channel, destination',
        (process_id,),
    ).fetchall()


def recent_movements(conn: sqlite3.Connection, process_id: int | None = None, limit: int = 20) -> list[sqlite3.Row]:
    if process_id is None:
        return conn.execute(
            '''
            SELECT m.*, p.label
              FROM movements m JOIN processes p ON p.id = m.process_id
             ORDER BY m.detected_at DESC, m.id DESC
             LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    return conn.execute(
        'SELECT * FROM movements WHERE process_id = ? ORDER BY detected_at DESC, id DESC LIMIT ?',
        (process_id, limit),
    ).fetchall()


def recent_notifications(conn: sqlite3.Connection, process_id: int | None = None, limit: int = 30) -> list[sqlite3.Row]:
    if process_id is None:
        return conn.execute(
            '''
            SELECT n.*, m.process_id, m.detected_at, p.label
              FROM notifications n
              JOIN movements m ON m.id = n.movement_id
              JOIN processes p ON p.id = m.process_id
             ORDER BY n.sent_at DESC, n.id DESC
             LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    return conn.execute(
        '''
        SELECT n.*, m.process_id, m.detected_at
          FROM notifications n
          JOIN movements m ON m.id = n.movement_id
         WHERE m.process_id = ?
         ORDER BY n.sent_at DESC, n.id DESC
         LIMIT ?
        ''',
        (process_id, limit),
    ).fetchall()


def due_processes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute('SELECT * FROM processes WHERE enabled = 1 ORDER BY id').fetchall()


def update_baseline(conn: sqlite3.Connection, process_id: int, snapshot_hash: str, text: str) -> None:
    now = utcnow_iso()
    conn.execute(
        '''
        UPDATE processes
           SET last_hash = ?, last_text = ?, last_checked_at = ?, last_error = NULL, updated_at = ?
         WHERE id = ?
        ''',
        (snapshot_hash, text, now, now, process_id),
    )
    conn.commit()


def update_no_change(conn: sqlite3.Connection, process_id: int) -> None:
    now = utcnow_iso()
    conn.execute(
        'UPDATE processes SET last_checked_at = ?, last_error = NULL, updated_at = ? WHERE id = ?',
        (now, now, process_id),
    )
    conn.commit()


def record_error(conn: sqlite3.Connection, process_id: int, error: str) -> None:
    now = utcnow_iso()
    conn.execute(
        'UPDATE processes SET last_checked_at = ?, last_error = ?, updated_at = ? WHERE id = ?',
        (now, error[:1000], now, process_id),
    )
    conn.commit()


def record_movement(
    conn: sqlite3.Connection,
    process_id: int,
    old_hash: str | None,
    new_hash: str,
    text: str,
    summary: str,
    diff: str,
) -> int:
    now = utcnow_iso()
    cur = conn.execute(
        '''
        INSERT INTO movements(process_id, detected_at, old_hash, new_hash, summary, diff)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (process_id, now, old_hash, new_hash, summary, diff),
    )
    movement_id = int(cur.lastrowid)
    conn.execute(
        '''
        UPDATE processes
           SET last_hash = ?, last_text = ?, last_checked_at = ?, last_changed_at = ?, last_error = NULL, updated_at = ?
         WHERE id = ?
        ''',
        (new_hash, text, now, now, now, process_id),
    )
    conn.commit()
    return movement_id


def record_notification(
    conn: sqlite3.Connection,
    movement_id: int,
    subscriber_id: int | None,
    channel: str,
    destination: str,
    status: str,
    error: str | None,
) -> None:
    conn.execute(
        '''
        INSERT INTO notifications(movement_id, subscriber_id, channel, destination, status, error, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        (movement_id, subscriber_id, channel, destination, status, error, utcnow_iso()),
    )
    conn.commit()

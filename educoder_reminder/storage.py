"""Transactional snapshots; retain old deadlines to detect postponements."""
import json
import sqlite3
from dataclasses import asdict


def save_snapshot(path, username, homeworks, now, *, scopes=None):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    connection = sqlite3.connect(path)
    try:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS homeworks (
                username TEXT NOT NULL, course_id TEXT NOT NULL,
                kind INTEGER NOT NULL, homework_id INTEGER NOT NULL,
                deadline TEXT, completed INTEGER, archived INTEGER NOT NULL,
                present INTEGER NOT NULL, payload TEXT NOT NULL, synced_at TEXT NOT NULL,
                PRIMARY KEY (username, course_id, kind, homework_id)
            );
            CREATE TABLE IF NOT EXISTS deadline_changes (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL, course_id TEXT NOT NULL,
                kind INTEGER NOT NULL, homework_id INTEGER NOT NULL,
                old_deadline TEXT, new_deadline TEXT, detected_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sync_state (
                username TEXT PRIMARY KEY, synced_at TEXT NOT NULL
            );
        ''')
        with connection:
            if scopes is None:
                connection.execute('UPDATE homeworks SET present=0 WHERE username=?', (username,))
                connection.execute('INSERT INTO sync_state VALUES (?, ?) ON CONFLICT(username) DO UPDATE SET synced_at=excluded.synced_at',
                                   (username, now.isoformat()))
            else:
                connection.executemany('UPDATE homeworks SET present=0 WHERE username=? AND course_id=? AND kind=?',
                                       [(username, course, kind) for course, kind in scopes])
            for item in homeworks:
                if scopes is not None and (item.course_id, item.kind) not in scopes:
                    raise ValueError('Homework outside refreshed scopes')
                key = (username, item.course_id, item.kind, item.id)
                previous = connection.execute(
                    'SELECT deadline FROM homeworks WHERE username=? AND course_id=? AND kind=? AND homework_id=?', key
                ).fetchone()
                if previous is not None and previous[0] != item.deadline:
                    connection.execute('''INSERT INTO deadline_changes
                        (username, course_id, kind, homework_id, old_deadline, new_deadline, detected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (*key, previous[0], item.deadline, now.isoformat()))
                connection.execute('''INSERT INTO homeworks
                    (username, course_id, kind, homework_id, deadline, completed, archived, present, payload, synced_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(username, course_id, kind, homework_id) DO UPDATE SET
                    deadline=excluded.deadline, completed=excluded.completed,
                    archived=excluded.archived, present=1, payload=excluded.payload,
                    synced_at=excluded.synced_at''',
                    (*key, item.deadline, item.completed, item.archived,
                     json.dumps(asdict(item), ensure_ascii=False), now.isoformat()))
    finally:
        connection.close()

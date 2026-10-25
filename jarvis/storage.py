"""SQLite storage shared by memory, reminders, profiles and the audit log.

One file, %APPDATA%\\Jarvis\\drexya.db. Safe to use from several threads: every call
takes a lock, and writes are committed immediately.
"""
import sqlite3
import threading

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id       INTEGER PRIMARY KEY,
    profile  TEXT NOT NULL DEFAULT 'default',
    category TEXT NOT NULL DEFAULT 'fact',
    text     TEXT NOT NULL,
    saved    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id       INTEGER PRIMARY KEY,
    profile  TEXT NOT NULL DEFAULT 'default',
    text     TEXT NOT NULL,
    due      TEXT NOT NULL,                     -- local time, 'YYYY-MM-DD HH:MM:SS'
    status   TEXT NOT NULL DEFAULT 'pending',   -- pending / fired / cancelled
    created  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id       INTEGER PRIMARY KEY,
    profile  TEXT NOT NULL DEFAULT 'default',
    text     TEXT NOT NULL,
    saved    TEXT NOT NULL
);

-- Extra people. The 'default' profile isn't stored here: it uses the main settings.
CREATE TABLE IF NOT EXISTS profiles (
    id        TEXT PRIMARY KEY,                 -- lowercase name, e.g. 'marcus'
    name      TEXT NOT NULL,                    -- as typed, e.g. 'Marcus'
    home_city TEXT NOT NULL DEFAULT '',
    created   TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path=None):
        self.path = str(path or config.DB_PATH)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def query(self, sql: str, params=()) -> list:
        """Run a SELECT and return the rows as dicts."""
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    def run(self, sql: str, params=()) -> int:
        """Run an INSERT/UPDATE/DELETE and commit. Returns the new row id (inserts) or rows changed."""
        with self._lock, self._db:
            cur = self._db.execute(sql, params)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    def close(self):
        with self._lock:
            self._db.close()

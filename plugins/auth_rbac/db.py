"""SQLite database connection management and schema initialization."""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    username    TEXT NOT NULL UNIQUE,
    email       TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'user'
                CHECK(role IN ('super_admin', 'business_admin', 'user')),
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    last_login  INTEGER DEFAULT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email != '';

CREATE TABLE IF NOT EXISTS profile_visibility (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name TEXT NOT NULL,
    user_id     TEXT DEFAULT NULL,
    granted_by  TEXT NOT NULL,
    granted_at  INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(profile_name, user_id)
);

CREATE INDEX IF NOT EXISTS idx_pv_user ON profile_visibility(user_id);
CREATE INDEX IF NOT EXISTS idx_pv_profile ON profile_visibility(profile_name);

CREATE TABLE IF NOT EXISTS login_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address  TEXT NOT NULL,
    username    TEXT DEFAULT '',
    success     INTEGER NOT NULL DEFAULT 0,
    attempted_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_la_ip_time ON login_attempts(ip_address, attempted_at);
"""


def get_db_path(config: dict | None = None) -> str:
    """Resolve the database path from config or env."""
    raw = os.environ.get("HERMES_RBAC_DB_PATH", "").strip()
    if not raw and config:
        raw = str(config.get("db_path", "") or "").strip()
    if not raw:
        raw = "~/.hermes/auth.db"
    return str(Path(raw).expanduser())


def init_db(db_path: str) -> None:
    """Initialize the database schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
    logger.info("auth_rbac: Database initialized at %s", db_path)


@contextmanager
def get_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Get a SQLite connection with WAL mode and row factory."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

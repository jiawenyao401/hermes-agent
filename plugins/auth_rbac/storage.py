"""SQLite storage backend for the Hermes RBAC plugin.

All database operations use aiosqlite for async SQLite access.
The database file lives at $HERMES_HOME/plugins/auth_rbac/rbac.db
(or ~/.hermes/plugins/auth_rbac/rbac.db by default).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

import aiosqlite

from .models import ProfileVisibility, Role, User

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('super_admin', 'business_admin', 'user')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS profile_visibility (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name TEXT NOT NULL,
    user_id TEXT,
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    UNIQUE(profile_name, user_id)
);
"""


def _default_db_path() -> Path:
    """Return the default path for the RBAC SQLite database."""
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    return Path(hermes_home) / "plugins" / "auth_rbac" / "rbac.db"


# ---------------------------------------------------------------------------
# Storage class
# ---------------------------------------------------------------------------


class RBACStorage:
    """Async SQLite storage for users and profile visibility."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or _default_db_path()
        self._db: Optional[aiosqlite.Connection] = None

    async def open(self) -> None:
        """Open the database connection and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        # Enable WAL mode for better concurrent read performance
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("RBACStorage not opened — call open() first")
        return self._db

    # -----------------------------------------------------------------------
    # Context-manager support
    # -----------------------------------------------------------------------

    async def __aenter__(self) -> RBACStorage:
        await self.open()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -----------------------------------------------------------------------
    # User CRUD
    # -----------------------------------------------------------------------

    async def create_user(self, user: User) -> User:
        """Insert a new user. Raises sqlite3.IntegrityError on duplicate."""
        row = user.to_row()
        await self.db.execute(
            """
            INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, last_login)
            VALUES (:id, :username, :email, :password_hash, :role, :is_active, :created_at, :last_login)
            """,
            row,
        )
        await self.db.commit()
        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Fetch a user by their UUID."""
        cursor = await self.db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return User.from_row(dict(row))

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Fetch a user by username (case-sensitive)."""
        cursor = await self.db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return User.from_row(dict(row))

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by email (case-insensitive)."""
        cursor = await self.db.execute(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return User.from_row(dict(row))

    async def update_user(self, user: User) -> None:
        """Update an existing user's mutable fields."""
        row = user.to_row()
        await self.db.execute(
            """
            UPDATE users
            SET username = :username,
                email = :email,
                password_hash = :password_hash,
                role = :role,
                is_active = :is_active,
                last_login = :last_login
            WHERE id = :id
            """,
            row,
        )
        await self.db.commit()

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user. Returns True if a row was deleted."""
        cursor = await self.db.execute(
            "DELETE FROM users WHERE id = ?", (user_id,)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def list_users(
        self,
        role: Optional[Role] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        """List users with optional filters."""
        clauses: list[str] = []
        params: list[object] = []
        if role is not None:
            clauses.append("role = ?")
            params.append(role.value)
        if is_active is not None:
            clauses.append("is_active = ?")
            params.append(int(is_active))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])
        cursor = await self.db.execute(
            f"SELECT * FROM users{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = await cursor.fetchall()
        return [User.from_row(dict(r)) for r in rows]

    async def count_users(self, role: Optional[Role] = None) -> int:
        """Count users, optionally filtered by role."""
        if role:
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM users WHERE role = ?", (role.value,)
            )
        else:
            cursor = await self.db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # -----------------------------------------------------------------------
    # Profile Visibility CRUD
    # -----------------------------------------------------------------------

    async def grant_profile_access(self, pv: ProfileVisibility) -> ProfileVisibility:
        """Grant a user access to a profile. Raises IntegrityError on duplicate."""
        cursor = await self.db.execute(
            """
            INSERT INTO profile_visibility (profile_name, user_id, granted_by, granted_at)
            VALUES (:profile_name, :user_id, :granted_by, :granted_at)
            """,
            pv.to_row(),
        )
        await self.db.commit()
        pv.id = cursor.lastrowid
        return pv

    async def revoke_profile_access(
        self, profile_name: str, user_id: Optional[str]
    ) -> bool:
        """Revoke a specific profile access grant."""
        cursor = await self.db.execute(
            "DELETE FROM profile_visibility WHERE profile_name = ? AND user_id IS ?",
            (profile_name, user_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_visible_profiles(self, user_id: str) -> list[str]:
        """Return the list of profile names visible to a given user.

        A user can see a profile if:
        - There is a grant with their specific user_id, OR
        - There is a grant with user_id IS NULL (public to all authenticated users).
        """
        cursor = await self.db.execute(
            """
            SELECT DISTINCT profile_name
            FROM profile_visibility
            WHERE user_id = ? OR user_id IS NULL
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [r["profile_name"] for r in rows]

    async def get_profile_grants(
        self, profile_name: str
    ) -> list[ProfileVisibility]:
        """List all access grants for a given profile."""
        cursor = await self.db.execute(
            "SELECT * FROM profile_visibility WHERE profile_name = ?",
            (profile_name,),
        )
        rows = await cursor.fetchall()
        return [ProfileVisibility.from_row(dict(r)) for r in rows]

    async def check_profile_access(
        self, profile_name: str, user_id: str
    ) -> bool:
        """Check whether a user has access to a specific profile."""
        cursor = await self.db.execute(
            """
            SELECT 1 FROM profile_visibility
            WHERE profile_name = ? AND (user_id = ? OR user_id IS NULL)
            LIMIT 1
            """,
            (profile_name, user_id),
        )
        row = await cursor.fetchone()
        return row is not None

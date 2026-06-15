"""Data access layer (CRUD) for users and profile visibility."""
from __future__ import annotations

import time
import uuid
from typing import Optional

from .db import get_connection
from .models import ProfileVisibility, User, VALID_ROLES
from .password import hash_password


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(
    db_path: str,
    *,
    username: str,
    email: str,
    password: str,
    role: str = "user",
) -> User:
    """Create a new user. Raises ValueError on duplicate username/email."""
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    now = int(time.time())
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password)

    with get_connection(db_path) as conn:
        # Check uniqueness
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            raise ValueError("Username already exists")

        if email:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                raise ValueError("Email already in use")

        conn.execute(
            """INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (user_id, username, email, pw_hash, role, now, now),
        )

    return User(
        id=user_id,
        username=username,
        email=email,
        password_hash=pw_hash,
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def get_user_by_id(db_path: str, user_id: str) -> Optional[User]:
    """Get user by ID."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_username(db_path: str, username: str) -> Optional[User]:
    """Get user by username."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return _row_to_user(row) if row else None


def list_users(
    db_path: str,
    *,
    page: int = 1,
    per_page: int = 50,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> tuple[list[User], int]:
    """List users with optional filtering. Returns (users, total)."""
    conditions = []
    params: list = []

    if role:
        conditions.append("role = ?")
        params.append(role)
    if is_active is not None:
        conditions.append("is_active = ?")
        params.append(1 if is_active else 0)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    with get_connection(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM users{where}", params).fetchone()[0]

        offset = (max(1, page) - 1) * max(1, per_page)
        rows = conn.execute(
            f"SELECT * FROM users{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

    return [_row_to_user(r) for r in rows], total


def update_user(db_path: str, user_id: str, **fields) -> Optional[User]:
    """Update user fields. Returns updated user or None."""
    allowed = {"username", "email", "password", "role", "is_active"}
    updates = {}
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k == "password":
                updates["password_hash"] = hash_password(v)
                updates["updated_at"] = int(time.time())
            elif k == "role":
                if v not in VALID_ROLES:
                    raise ValueError(f"Invalid role: {v}")
                updates["role"] = v
                updates["updated_at"] = int(time.time())
            elif k == "is_active":
                updates["is_active"] = 1 if v else 0
                updates["updated_at"] = int(time.time())
            else:
                updates[k] = v
                updates["updated_at"] = int(time.time())

    if not updates:
        return get_user_by_id(db_path, user_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [user_id]

    with get_connection(db_path) as conn:
        # Check uniqueness for username/email
        if "username" in updates:
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (updates["username"], user_id),
            ).fetchone()
            if existing:
                raise ValueError("Username already exists")

        if "email" in updates and updates["email"]:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (updates["email"], user_id),
            ).fetchone()
            if existing:
                raise ValueError("Email already in use")

        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)

    return get_user_by_id(db_path, user_id)


def delete_user(db_path: str, user_id: str) -> bool:
    """Delete a user. Returns True if deleted."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cursor.rowcount > 0


def update_last_login(db_path: str, user_id: str) -> None:
    """Update the last_login timestamp."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (int(time.time()), user_id),
        )


def count_super_admins(db_path: str) -> int:
    """Count active super_admin users."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'super_admin' AND is_active = 1"
        ).fetchone()
        return row[0]


def is_user_active(db_path: str, user_id: str) -> bool:
    """Check if a user is active."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return bool(row and row[0])


# ---------------------------------------------------------------------------
# Profile Visibility CRUD
# ---------------------------------------------------------------------------

def get_profile_visibility(db_path: str, profile_name: str) -> list[ProfileVisibility]:
    """Get all visibility records for a profile."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM profile_visibility WHERE profile_name = ? ORDER BY id",
            (profile_name,),
        ).fetchall()
    return [_row_to_pv(r) for r in rows]


def get_user_visible_profiles(db_path: str, user_id: str) -> list[str]:
    """Get profile names visible to a specific user (including global)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT DISTINCT profile_name FROM profile_visibility
               WHERE user_id IS NULL OR user_id = ?
               ORDER BY profile_name""",
            (user_id,),
        ).fetchall()
    return [r[0] for r in rows]


def set_profile_visibility(
    db_path: str,
    profile_name: str,
    user_ids: list[str],
    global_visibility: bool,
    granted_by: str,
) -> None:
    """Set profile visibility. Replaces existing records."""
    now = int(time.time())

    with get_connection(db_path) as conn:
        # Remove existing records for this profile
        conn.execute(
            "DELETE FROM profile_visibility WHERE profile_name = ?",
            (profile_name,),
        )

        if global_visibility:
            # Global visibility (user_id IS NULL)
            conn.execute(
                """INSERT INTO profile_visibility (profile_name, user_id, granted_by, granted_at)
                   VALUES (?, NULL, ?, ?)""",
                (profile_name, granted_by, now),
            )
        elif user_ids:
            # Specific users
            for uid in user_ids:
                conn.execute(
                    """INSERT INTO profile_visibility (profile_name, user_id, granted_by, granted_at)
                       VALUES (?, ?, ?, ?)""",
                    (profile_name, uid, granted_by, now),
                )
        # else: no visibility records = only super_admin can see


def delete_profile_visibility(db_path: str, profile_name: str) -> None:
    """Delete all visibility records for a profile."""
    with get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM profile_visibility WHERE profile_name = ?",
            (profile_name,),
        )


def can_user_access_profile(db_path: str, user_id: str, profile_name: str) -> bool:
    """Check if a user can access a specific profile."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM profile_visibility
               WHERE profile_name = ? AND (user_id IS NULL OR user_id = ?)""",
            (profile_name, user_id),
        ).fetchone()
        return row[0] > 0


# ---------------------------------------------------------------------------
# Login Attempts (rate limiting persistence)
# ---------------------------------------------------------------------------

def record_login_attempt(db_path: str, ip: str, username: str, success: bool) -> None:
    """Record a login attempt."""
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO login_attempts (ip_address, username, success, attempted_at)
               VALUES (?, ?, ?, ?)""",
            (ip, username, 1 if success else 0, int(time.time())),
        )


def cleanup_old_login_attempts(db_path: str, max_age_seconds: int = 3600) -> None:
    """Remove login attempts older than max_age_seconds."""
    cutoff = int(time.time()) - max_age_seconds
    with get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM login_attempts WHERE attempted_at < ?", (cutoff,)
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_user(row) -> User:
    """Convert a sqlite3.Row to a User."""
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login=row["last_login"],
    )


def _row_to_pv(row) -> ProfileVisibility:
    """Convert a sqlite3.Row to a ProfileVisibility."""
    return ProfileVisibility(
        id=row["id"],
        profile_name=row["profile_name"],
        user_id=row["user_id"],
        granted_by=row["granted_by"],
        granted_at=row["granted_at"],
    )

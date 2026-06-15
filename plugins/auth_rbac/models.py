"""Data models for the Hermes RBAC plugin."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Role(str, Enum):
    """User roles in the RBAC system."""

    SUPER_ADMIN = "super_admin"
    BUSINESS_ADMIN = "business_admin"
    USER = "user"

    @classmethod
    def hierarchy(cls) -> dict[Role, int]:
        """Return role hierarchy (higher number = more privileges)."""
        return {
            cls.USER: 0,
            cls.BUSINESS_ADMIN: 1,
            cls.SUPER_ADMIN: 2,
        }

    def level(self) -> int:
        """Get the privilege level for this role."""
        return self.hierarchy().get(self, -1)

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level() >= other.level()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level() > other.level()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level() <= other.level()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level() < other.level()


# Convenience constant used by sibling modules (repository, __init__)
VALID_ROLES: set[str] = {r.value for r in Role}


@dataclass
class User:
    """A user in the RBAC system."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    email: str = ""
    password_hash: str = ""
    role: Role = Role.USER
    is_active: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_login: Optional[str] = None

    def to_row(self) -> dict:
        """Serialize to a dict suitable for SQLite insertion."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "password_hash": self.password_hash,
            "role": self.role.value,
            "is_active": int(self.is_active),
            "created_at": self.created_at,
            "last_login": self.last_login,
        }

    @classmethod
    def from_row(cls, row: dict) -> User:
        """Deserialize from a SQLite row dict."""
        return cls(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=Role(row["role"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            last_login=row.get("last_login"),
        )

    def public_dict(self) -> dict:
        """Return a safe representation (no password hash)."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }


@dataclass
class ProfileVisibility:
    """Controls which users can access a Hermes profile."""

    id: Optional[int] = None
    profile_name: str = ""
    user_id: Optional[str] = None  # None = public to all authenticated users
    granted_by: str = ""
    granted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_row(self) -> dict:
        """Serialize to a dict suitable for SQLite insertion."""
        return {
            "id": self.id,
            "profile_name": self.profile_name,
            "user_id": self.user_id,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> ProfileVisibility:
        """Deserialize from a SQLite row dict."""
        return cls(
            id=row.get("id"),
            profile_name=row["profile_name"],
            user_id=row.get("user_id"),
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )

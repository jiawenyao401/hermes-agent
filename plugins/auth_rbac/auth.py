"""Authentication logic for the Hermes RBAC plugin.

Password hashing: hashlib.scrypt (stdlib, no external deps)
Token signing: HMAC-SHA256
Login rate-limiting: in-memory sliding-window counter
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime, timezone
from typing import Optional

from .models import Role, User
from .storage import RBACStorage

# ---------------------------------------------------------------------------
# Password hashing (hashlib.scrypt)
# ---------------------------------------------------------------------------

_SCRYPT_N = 2**14  # CPU/memory cost (16384)
_SCRYPT_R = 8      # block size
_SCRYPT_P = 1      # parallelization
_SALT_LEN = 16     # bytes


def hash_password(password: str) -> str:
    """Hash a password with scrypt.

    Returns a storable string in the format:
        scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>
    """
    salt = os.urandom(_SALT_LEN)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored scrypt hash.

    Returns True if the password matches.
    """
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = bytes.fromhex(parts[4])
        expected = bytes.fromhex(parts[5])
    except (ValueError, IndexError):
        return False

    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
    )
    return hmac.compare_digest(dk, expected)


# ---------------------------------------------------------------------------
# HMAC token generation & verification
# ---------------------------------------------------------------------------

_TOKEN_VERSION = 1


def _get_signing_key() -> bytes:
    """Return (or generate) the HMAC signing key.

    The key is stored in $HERMES_HOME/plugins/auth_rbac/.token_key.
    If the file doesn't exist, a new 32-byte key is created.
    """
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    key_path = os.path.join(hermes_home, "plugins", "auth_rbac", ".token_key")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            key = f.read().strip()
            if len(key) >= 32:
                return key
    # Generate new key
    key = secrets.token_hex(32).encode("ascii")
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(key)
    os.chmod(key_path, 0o600)
    return key


def generate_token(user_id: str, role: str, ttl_seconds: int = 86400) -> str:
    """Generate a signed authentication token.

    Token format: v<version>.<expiry_epoch>.<user_id>.<role>.<signature>

    The signature covers: version|expiry|user_id|role
    """
    expiry = int(time.time()) + ttl_seconds
    payload = f"{_TOKEN_VERSION}|{expiry}|{user_id}|{role}"
    key = _get_signing_key()
    sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v{_TOKEN_VERSION}.{expiry}.{user_id}.{role}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """Verify a token and return its claims, or None if invalid/expired.

    Returns dict with keys: user_id, role, expiry
    """
    try:
        parts = token.split(".")
        if len(parts) != 5:
            return None
        version_str, expiry_str, user_id, role, sig = parts
        version = int(version_str.lstrip("v"))
        expiry = int(expiry_str)
        if version != _TOKEN_VERSION:
            return None
        if expiry < int(time.time()):
            return None  # expired
        payload = f"{version}|{expiry}|{user_id}|{role}"
        key = _get_signing_key()
        expected = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return {"user_id": user_id, "role": role, "expiry": expiry}
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Login rate limiting (sliding window, in-memory)
# ---------------------------------------------------------------------------

class LoginRateLimiter:
    """Sliding-window rate limiter for login attempts.

    Tracks failed attempts per username and per IP address.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        lockout_seconds: int = 600,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        # {key: list[timestamp]}
        self._attempts: dict[str, list[float]] = {}

    def _cleanup(self, key: str) -> None:
        """Remove expired entries for a key."""
        if key not in self._attempts:
            return
        cutoff = time.time() - self.window_seconds
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        if not self._attempts[key]:
            del self._attempts[key]

    def is_blocked(self, key: str) -> bool:
        """Check if a key (username or IP) is currently blocked."""
        self._cleanup(key)
        return len(self._attempts.get(key, [])) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        """Record a failed login attempt."""
        self._cleanup(key)
        self._attempts.setdefault(key, []).append(time.time())

    def record_success(self, key: str) -> None:
        """Clear attempt history on successful login."""
        self._attempts.pop(key, None)

    def remaining_attempts(self, key: str) -> int:
        """How many attempts remain before lockout."""
        self._cleanup(key)
        return max(0, self.max_attempts - len(self._attempts.get(key, [])))


# ---------------------------------------------------------------------------
# High-level auth operations
# ---------------------------------------------------------------------------


class Authenticator:
    """High-level authentication operations backed by RBACStorage."""

    def __init__(self, storage: RBACStorage) -> None:
        self.storage = storage
        self.rate_limiter = LoginRateLimiter()

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        role: Role = Role.USER,
    ) -> User:
        """Register a new user.

        Raises ValueError on validation failure.
        Raises sqlite3.IntegrityError if username or email already exists.
        """
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if "@" not in email:
            raise ValueError("Invalid email address")

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        return await self.storage.create_user(user)

    async def login(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
    ) -> Optional[str]:
        """Authenticate a user and return a token.

        Returns None if authentication fails. Also handles rate limiting.
        """
        rate_key = username.lower()
        if ip_address:
            # Check both username and IP
            if self.rate_limiter.is_blocked(rate_key):
                return None
            if self.rate_limiter.is_blocked(f"ip:{ip_address}"):
                return None

        user = await self.storage.get_user_by_username(username)
        if user is None:
            # Still record the failure for rate limiting
            self.rate_limiter.record_failure(rate_key)
            if ip_address:
                self.rate_limiter.record_failure(f"ip:{ip_address}")
            return None

        if not user.is_active:
            return None

        if not verify_password(password, user.password_hash):
            self.rate_limiter.record_failure(rate_key)
            if ip_address:
                self.rate_limiter.record_failure(f"ip:{ip_address}")
            return None

        # Success — clear failures
        self.rate_limiter.record_success(rate_key)
        if ip_address:
            self.rate_limiter.record_success(f"ip:{ip_address}")

        # Update last_login
        user.last_login = datetime.now(timezone.utc).isoformat()
        await self.storage.update_user(user)

        return generate_token(user.id, user.role.value)

    async def init_admin_from_env(self) -> Optional[User]:
        """Create the initial super-admin from environment variables.

        Env vars:
            HERMES_RBAC_INIT_ADMIN_USERNAME
            HERMES_RBAC_INIT_ADMIN_PASSWORD
            HERMES_RBAC_INIT_ADMIN_EMAIL

        Returns the created user, or None if env vars are not set.
        Skips silently if the admin already exists.
        """
        username = os.environ.get("HERMES_RBAC_INIT_ADMIN_USERNAME")
        password = os.environ.get("HERMES_RBAC_INIT_ADMIN_PASSWORD")
        email = os.environ.get("HERMES_RBAC_INIT_ADMIN_EMAIL")

        if not all([username, password, email]):
            return None

        assert username is not None
        assert password is not None
        assert email is not None

        # Check if already exists
        existing = await self.storage.get_user_by_username(username)
        if existing:
            return existing

        try:
            return await self.register(username, email, password, Role.SUPER_ADMIN)
        except Exception:
            # May fail if email also matches; try fetch by email
            return await self.storage.get_user_by_email(email)

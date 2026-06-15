"""Password hashing and verification using stdlib hashlib.scrypt.

Reuses the same format and parameters as the basic auth provider:
    scrypt$N$r$p$<salt_b64>$<dk_b64>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# scrypt parameters (RFC 7914)
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_BYTES = 16

# Dummy hash for constant-time verify on unknown usernames
_DUMMY_HASH: str | None = None


def hash_password(password: str) -> str:
    """Return a ``scrypt$n$r$p$<salt_b64>$<dk_b64>`` hash string."""
    salt = secrets.token_bytes(_SCRYPT_SALT_BYTES)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=0,
    )
    return (
        f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time scrypt verify. False on any malformed hash string."""
    try:
        scheme, n_s, r_s, p_s, salt_b64, dk_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError):
        return False
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=0,
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


def get_dummy_hash() -> str:
    """Return a fixed dummy hash for constant-time verify on unknown users."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-password-for-constant-time-verify")
    return _DUMMY_HASH

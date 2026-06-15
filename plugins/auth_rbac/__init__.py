"""auth_rbac — Multi-user dashboard auth with RBAC plugin.

This plugin replaces the basic auth provider with a SQLite-backed
multi-user system supporting super_admin / business_admin / user roles.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Plugin entry — registers RBACAuthProvider when enabled.

    1. Check if RBAC is enabled via env vars or config
    2. Initialize SQLite database
    3. Create RBACAuthProvider instance
    4. Register as DashboardAuthProvider
    5. Ensure initial super_admin exists
    """
    from .db import init_db, get_db_path
    from .provider import RBACAuthProvider

    # Check if RBAC is enabled
    enabled = os.environ.get("HERMES_RBAC_ENABLED", "").strip().lower()
    if not enabled:
        # Also check config.yaml
        try:
            from hermes_cli.config import cfg_get, load_config
            cfg = load_config()
            rbac_cfg = cfg_get(cfg, "dashboard", "rbac", default=None)
            if isinstance(rbac_cfg, dict):
                enabled = str(rbac_cfg.get("enabled", "")).strip().lower()
        except Exception:
            pass

    if enabled not in ("true", "1", "yes"):
        logger.debug("auth_rbac: RBAC not enabled, skipping registration")
        return

    # Resolve config
    config = _load_config()

    # Initialize database
    db_path = get_db_path(config)
    init_db(db_path)

    # Ensure initial super_admin
    _ensure_initial_admin(db_path, config)

    # Create provider
    secret = _resolve_secret(config)
    access_ttl = int(config.get("access_ttl_seconds", 900))
    refresh_ttl = int(config.get("refresh_ttl_seconds", 2592000))
    rate_limit = int(config.get("rate_limit_per_minute", 5))

    provider = RBACAuthProvider(
        db_path=db_path,
        secret=secret,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        rate_limit_per_minute=rate_limit,
    )

    ctx.register_dashboard_auth_provider(provider)
    logger.info("auth_rbac: registered RBAC auth provider")


def _load_config() -> dict:
    """Load RBAC config from config.yaml dashboard.rbac section."""
    try:
        from hermes_cli.config import cfg_get, load_config
        cfg = load_config()
        section = cfg_get(cfg, "dashboard", "rbac", default=None)
        if isinstance(section, dict):
            return section
    except Exception:
        pass
    return {}


def _resolve_secret(config: dict) -> bytes:
    """Resolve the token-signing secret."""
    import base64
    import secrets

    raw = os.environ.get("HERMES_RBAC_SECRET", "").strip()
    if not raw:
        raw = str(config.get("secret", "") or "").strip()

    if not raw:
        logger.info(
            "auth_rbac: no 'secret' configured; generating random per-process key. "
            "Sessions will not survive restart. Set HERMES_RBAC_SECRET or "
            "dashboard.rbac.secret for stable sessions."
        )
        return secrets.token_bytes(32)

    for decoder in (base64.b64decode, bytes.fromhex):
        try:
            decoded = decoder(raw)
            if len(decoded) >= 16:
                return decoded
        except (ValueError, TypeError):
            pass
    return raw.encode("utf-8")


def _ensure_initial_admin(db_path: str, config: dict) -> None:
    """Create initial super_admin from env vars if no super_admin exists."""
    from .db import get_connection
    from .models import User
    from .password import hash_password

    username = os.environ.get("HERMES_RBAC_INIT_ADMIN_USERNAME", "").strip()
    password = os.environ.get("HERMES_RBAC_INIT_ADMIN_PASSWORD", "").strip()
    email = os.environ.get("HERMES_RBAC_INIT_ADMIN_EMAIL", "").strip()

    # Also check config
    admin_cfg = config.get("initial_admin", {})
    if isinstance(admin_cfg, dict):
        if not username:
            username = str(admin_cfg.get("username", "")).strip()
        if not password:
            password = str(admin_cfg.get("password", "")).strip()
        if not email:
            email = str(admin_cfg.get("email", "")).strip()

    if not username or not password:
        # Check if any super_admin exists
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'super_admin'"
            ).fetchone()
            if row[0] == 0:
                logger.warning(
                    "auth_rbac: No super_admin exists and no initial admin "
                    "configured. Set HERMES_RBAC_INIT_ADMIN_USERNAME and "
                    "HERMES_RBAC_INIT_ADMIN_PASSWORD, or configure "
                    "dashboard.rbac.initial_admin in config.yaml."
                )
        return

    # Check if this username already exists
    with get_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT id, role FROM users WHERE username = ?", (username,)
        ).fetchone()

        if existing:
            if existing[1] != "super_admin":
                # Promote to super_admin
                conn.execute(
                    "UPDATE users SET role = 'super_admin' WHERE id = ?",
                    (existing[0],),
                )
                logger.info(
                    "auth_rbac: Promoted existing user '%s' to super_admin", username
                )
            return

        # Create new super_admin
        import uuid
        import time

        user_id = str(uuid.uuid4())
        pw_hash = hash_password(password)
        now = int(time.time())

        conn.execute(
            """INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'super_admin', 1, ?, ?)""",
            (user_id, username, email, pw_hash, now, now),
        )
        logger.info("auth_rbac: Created initial super_admin user '%s'", username)

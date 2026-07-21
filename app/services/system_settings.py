"""DB-backed system settings with env fallback and encrypted secrets."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import structlog
from sqlalchemy.orm import Session

from app.models import SystemSetting
from app.security.secrets import encrypt_value, mask_secret, try_decrypt_value
from app.services.settings_schema import (
    ENV_KEY_MAP,
    SECRET_KEYS,
    SETTING_CATEGORIES,
    SETTING_DEFAULTS,
)

UNCHANGED = "__UNCHANGED__"

log = structlog.get_logger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _coerce_value(key: str, value: Any) -> Any:
    if key in {"port", "request_timeout_seconds", "poll_interval_seconds"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if key in {"require_agent_token"}:
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}
    return value


def _env_value(category: str, field: str) -> str | None:
    env_name = ENV_KEY_MAP.get(category, {}).get(field)
    if env_name:
        val = os.getenv(env_name)
        if val is not None and val != "":
            return val
    return None


def _load_row(db: Session, category: str) -> SystemSetting | None:
    return db.query(SystemSetting).filter(SystemSetting.category == category).first()


def _stored_config(db: Session, category: str) -> dict:
    row = _load_row(db, category)
    if not row or not row.config_json:
        return {}
    try:
        return json.loads(row.config_json)
    except json.JSONDecodeError:
        return {}


def _decrypt_config(category: str, config: dict) -> dict:
    out = dict(config)
    for key in SECRET_KEYS.get(category, set()):
        if key not in out or not out[key]:
            continue
        plain, err = try_decrypt_value(out[key])
        if err:
            log.info(
                "settings.secret_stale",
                category=category,
                field=key,
                hint="Re-save in Settings or set the matching environment variable",
            )
            out.pop(key, None)
        else:
            out[key] = plain
    return out


def _encrypt_config(category: str, config: dict) -> dict:
    out = dict(config)
    for key in SECRET_KEYS.get(category, set()):
        if key in out and out[key]:
            out[key] = encrypt_value(out[key])
    return out


def _merge_with_env(category: str, stored: dict) -> tuple[dict, dict[str, str]]:
    """Return effective config and per-field source map (database|environment|default)."""
    defaults = dict(SETTING_DEFAULTS[category])
    sources: dict[str, str] = {}
    effective = dict(defaults)

    for field, default in defaults.items():
        env_val = _env_value(category, field)
        if env_val is not None and env_val != "":
            effective[field] = _coerce_value(field, env_val)
            sources[field] = "environment"

    for field, value in stored.items():
        if value is None or value == "":
            continue
        if field in SECRET_KEYS.get(category, set()):
            plain, err = try_decrypt_value(value)
            if err:
                log.info(
                    "settings.secret_stale",
                    category=category,
                    field=field,
                    hint="Using environment fallback when available",
                )
                if sources.get(field) != "environment":
                    sources[field] = "unavailable"
            elif plain:
                effective[field] = plain
                sources[field] = "database"
        else:
            effective[field] = _coerce_value(field, value)
            sources[field] = "database"

    for field in defaults:
        if field not in sources:
            sources[field] = "default"

    return effective, sources


def get_category_settings(db: Session, category: str, *, masked: bool = True) -> dict:
    if category not in SETTING_CATEGORIES:
        raise ValueError(f"Unknown settings category: {category}")

    stored = _stored_config(db, category)
    effective, sources = _merge_with_env(category, stored)
    row = _load_row(db, category)

    payload = {}
    for field, value in effective.items():
        if masked and field in SECRET_KEYS.get(category, set()):
            payload[field] = mask_secret(value) if value else ""
            payload[f"{field}_set"] = bool(value)
        else:
            payload[field] = value
        payload[f"{field}_source"] = sources.get(field, "default")

    payload["updated_at"] = row.updated_at.isoformat() if row and row.updated_at else None
    payload["stored_in_database"] = bool(row)
    return payload


def get_all_settings(db: Session, *, masked: bool = True) -> dict:
    return {
        category: get_category_settings(db, category, masked=masked)
        for category in SETTING_CATEGORIES
    }


def get_effective_config(db: Session, category: str) -> dict:
    stored = _stored_config(db, category)
    effective, _ = _merge_with_env(category, stored)
    return effective


def save_category_settings(db: Session, category: str, updates: dict) -> dict:
    if category not in SETTING_CATEGORIES:
        raise ValueError(f"Unknown settings category: {category}")

    current_stored = _decrypt_config(category, _stored_config(db, category))
    merged = dict(current_stored)

    for field, value in updates.items():
        if field.endswith("_source") or field.endswith("_set"):
            continue
        if field not in SETTING_DEFAULTS[category]:
            continue
        if value == UNCHANGED:
            continue
        if field in SECRET_KEYS.get(category, set()) and (value is None or value == ""):
            continue
        merged[field] = _coerce_value(field, value)

    encrypted = _encrypt_config(category, merged)
    row = _load_row(db, category)
    if row:
        row.config_json = json.dumps(encrypted)
        row.updated_at = _now()
    else:
        row = SystemSetting(
            id=str(uuid.uuid4()),
            category=category,
            config_json=json.dumps(encrypted),
            updated_at=_now(),
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return get_category_settings(db, category, masked=True)


def build_database_url(config: dict) -> str:
    dialect = config.get("dialect") or "postgresql"
    user = quote_plus(config.get("username") or "")
    password = quote_plus(config.get("password") or "")
    host = config.get("host") or "localhost"
    port = config.get("port") or 5432
    database = config.get("database") or "azure_cost_db"
    ssl = config.get("ssl_mode") or "prefer"

    if dialect == "sqlite":
        return f"sqlite:///{database}"

    auth = ""
    if user:
        auth = user
        if password:
            auth = f"{user}:{password}"
        auth = f"{auth}@"

    url = f"{dialect}://{auth}{host}:{port}/{database}"
    if dialect.startswith("postgres") and ssl and ssl != "disable":
        url += f"?sslmode={ssl}"
    return url


def test_azure_connection(config: dict) -> dict:
    import requests
    from app.auth import build_credential

    mode = config.get("auth_mode") or "managed_identity"
    try:
        cred = build_credential({**config, "auth_mode": mode})
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:
        return {"ok": False, "message": f"Could not create Azure credential: {exc}"}

    try:
        token = cred.get_token("https://management.azure.com/.default")
    except Exception as exc:
        return {"ok": False, "message": f"Token request failed: {exc}"}

    resp = requests.get(
        "https://management.azure.com/subscriptions?api-version=2022-12-01",
        headers={"Authorization": f"Bearer {token.token}"},
        timeout=30,
    )
    if resp.status_code >= 400:
        return {"ok": False, "message": f"Azure API returned {resp.status_code}"}

    count = len(resp.json().get("value", []))
    mode_label = "Managed identity" if mode == "managed_identity" else mode.replace("_", " ").title()
    return {
        "ok": True,
        "message": f"{mode_label} connected successfully. {count} subscription(s) visible.",
    }


def test_database_connection(config: dict) -> dict:
    from sqlalchemy import create_engine, text

    url = build_database_url(config)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    test_engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    with test_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "message": "Database connection succeeded.", "connection_url": mask_database_url(url)}


def mask_database_url(url: str) -> str:
    if "@" not in url:
        return url
    prefix, suffix = url.split("@", 1)
    if "://" in prefix:
        scheme, rest = prefix.split("://", 1)
        if ":" in rest:
            user = rest.split(":", 1)[0]
            return f"{scheme}://{user}:****@{suffix}"
    return f"****@{suffix}"


def apply_database_connection(db: Session) -> dict:
    """Switch the live SQLAlchemy engine to the stored database settings."""
    from app.database import (
        SessionLocal,
        get_active_database_url,
        migrate_schema,
        reconfigure_engine,
    )

    config = get_effective_config(db, "database")
    new_url = build_database_url(config)
    old_url = get_active_database_url()

    if new_url == old_url:
        return {
            "ok": True,
            "message": "Already using the configured database connection.",
            "connection_url": mask_database_url(new_url),
        }

    exported = db.query(SystemSetting).all()
    snapshot = [
        {"id": row.id, "category": row.category, "config_json": row.config_json}
        for row in exported
    ]

    reconfigure_engine(new_url)
    migrate_schema()

    if snapshot:
        new_db = SessionLocal()
        try:
            for row in snapshot:
                existing = new_db.query(SystemSetting).filter(
                    SystemSetting.category == row["category"]
                ).first()
                if existing:
                    existing.config_json = row["config_json"]
                else:
                    new_db.add(SystemSetting(
                        id=row["id"],
                        category=row["category"],
                        config_json=row["config_json"],
                    ))
            new_db.commit()
        finally:
            new_db.close()

    return {
        "ok": True,
        "message": "Database connection applied. New requests use the configured database.",
        "connection_url": mask_database_url(new_url),
    }

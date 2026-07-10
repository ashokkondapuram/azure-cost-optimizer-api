"""Runtime configuration loaded from DB settings with env fallback."""
from __future__ import annotations

import threading

_lock = threading.Lock()
_cache: dict = {}


def invalidate_runtime_config() -> None:
    with _lock:
        _cache.clear()


def _with_db(loader):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return loader(db)
    finally:
        db.close()


def get_cors_origins() -> list[str]:
    with _lock:
        if "cors_origins" in _cache:
            return _cache["cors_origins"]

    from app.settings import get_settings
    from app.services.system_settings import get_effective_config

    origins = list(get_settings().cors_allowed_origins)
    try:
        app_cfg = _with_db(lambda db: get_effective_config(db, "application"))
        raw = (app_cfg.get("cors_allowed_origins") or "").strip()
        if raw:
            origins = [o.strip() for o in raw.split(",") if o.strip()]
    except (ValueError, KeyError, AttributeError, TypeError):
        pass

    with _lock:
        _cache["cors_origins"] = origins
    return origins


def get_request_timeout_seconds() -> int:
    with _lock:
        if "request_timeout" in _cache:
            return _cache["request_timeout"]

    from app.settings import get_settings
    from app.services.system_settings import get_effective_config

    timeout = get_settings().request_timeout_seconds
    try:
        app_cfg = _with_db(lambda db: get_effective_config(db, "application"))
        if app_cfg.get("request_timeout_seconds") is not None:
            timeout = int(app_cfg["request_timeout_seconds"])
    except (ValueError, KeyError, AttributeError, TypeError):
        pass

    with _lock:
        _cache["request_timeout"] = timeout
    return timeout


def get_runtime_status() -> dict:
    from app.database import get_active_database_url, get_bootstrap_database_url
    from app.platform import get_deployment_context, get_app_service_database_url
    from app.security.secrets import encryption_status
    from app.services.system_settings import get_effective_config, mask_database_url, build_database_url

    deployment = get_deployment_context()
    stored_db = False
    stored_url = None
    azure_auth_mode = None
    try:
        db_cfg = _with_db(lambda db: get_effective_config(db, "database"))
        stored_db = any(db_cfg.get(k) for k in ("host", "database", "username"))
        if stored_db:
            stored_url = mask_database_url(build_database_url(db_cfg))
        azure_auth_mode = _with_db(lambda db: get_effective_config(db, "azure").get("auth_mode"))
    except (ValueError, KeyError, AttributeError, TypeError):
        pass

    from app.ai_client import build_ai_config

    cors = get_cors_origins()
    enc = encryption_status()
    app_service_db = get_app_service_database_url()
    ai_cfg = None
    ai_ready = False
    try:
        ai_cfg = _with_db(lambda db: get_effective_config(db, "ai"))
        ai_ready = bool(build_ai_config(ai_cfg))
    except (ValueError, KeyError, AttributeError, TypeError):
        pass

    from app.cost_export import export_config_summary
    from app.operations_scheduler import get_scheduler_status

    return {
        "deployment": deployment,
        "azure": {
            "auth_mode": azure_auth_mode or deployment.get("recommended_azure_auth") or "managed_identity",
        },
        "ai": {
            "enabled": bool(ai_cfg and ai_cfg.get("ai_enabled", True)),
            "configured": ai_ready,
            "deployment": (ai_cfg or {}).get("openai_deployment") or "",
            "endpoint_set": bool((ai_cfg or {}).get("openai_endpoint")),
        },
        "cost_export": export_config_summary(),
        "database": {
            "bootstrap_url": mask_database_url(get_bootstrap_database_url()),
            "active_url": mask_database_url(get_active_database_url()),
            "stored_config": stored_db,
            "stored_url": stored_url,
            "app_service_connection_configured": bool(app_service_db),
            "note": (
                "Connected via App Service connection string."
                if app_service_db
                else "Set DATABASE_URL or POSTGRESQLCONNSTR_* in App Service configuration."
            ) if deployment.get("is_app_service") else "Uses local SQLite when DATABASE_URL is unset.",
        },
        "cors": {
            "active_origins": cors,
            "hot_reload": True,
        },
        "encryption": enc,
        "scheduled_operations": get_scheduler_status(),
    }

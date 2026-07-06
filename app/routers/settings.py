"""Settings router — /settings prefix."""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.runtime_config import invalidate_runtime_config, get_runtime_status
from app.services.settings_schema import SETTING_CATEGORIES
from app.services.system_settings import (
    apply_database_connection,
    build_database_url,
    get_all_settings,
    get_category_settings,
    get_effective_config as get_system_config,
    mask_database_url,
    save_category_settings,
    test_azure_connection,
    test_database_connection,
)
from app.ai_client import verify_ai_connection
from app.user_auth import require_admin_user
import app.auth as azure_auth
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/settings", tags=["Settings"])


class AzureSettingsIn(BaseModel):
    auth_mode: Optional[str] = Field(None, description="managed_identity | default_credential | service_principal")
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = Field(None, description="Leave blank to keep the stored secret")
    default_subscription_id: Optional[str] = None


class DatabaseSettingsIn(BaseModel):
    dialect: Optional[str] = Field("postgresql", description="postgresql | sqlite")
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = Field(None, description="Leave blank to keep the stored password")
    ssl_mode: Optional[str] = None


class ApplicationSettingsIn(BaseModel):
    app_env: Optional[str] = None
    cors_allowed_origins: Optional[str] = None
    request_timeout_seconds: Optional[int] = None
    log_level: Optional[str] = None


class KubernetesSettingsIn(BaseModel):
    agent_token: Optional[str] = Field(None, description="Leave blank to keep the stored token")
    require_agent_token: Optional[bool] = None


class AiSettingsIn(BaseModel):
    ai_enabled: Optional[bool] = None
    ai_auth_mode: Optional[str] = Field(None, description="api_key | azure_ad")
    openai_key: Optional[str] = Field(None, description="Leave blank to keep the stored key")
    openai_endpoint: Optional[str] = None
    openai_deployment: Optional[str] = None
    openai_api_version: Optional[str] = None
    ai_enrich_all_findings: Optional[bool] = None
    ai_max_findings_per_run: Optional[int] = Field(None, ge=1, le=200)
    ai_batch_size: Optional[int] = Field(None, ge=1, le=25)


@router.get("/status", summary="Runtime status for database, CORS, and encryption")
def settings_status(request: Request):
    require_admin_user(request)
    return get_runtime_status()


@router.get("", summary="Get all system settings (secrets masked)")
def list_all_settings(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    return get_all_settings(db, masked=True)


@router.get("/{category}", summary="Get settings for a category")
def get_settings_category(request: Request, category: str = Path(...), db: Session = Depends(get_db)):
    require_admin_user(request)
    if category not in SETTING_CATEGORIES:
        raise HTTPException(404, f"Unknown category. Valid: {list(SETTING_CATEGORIES)}")
    return get_category_settings(db, category, masked=True)


@router.put("/{category}", summary="Save settings for a category to the database")
def put_settings_category(
    request: Request,
    category: str = Path(...),
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    if category not in SETTING_CATEGORIES:
        raise HTTPException(404, f"Unknown category. Valid: {list(SETTING_CATEGORIES)}")
    try:
        saved = save_category_settings(db, category, body)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    if category == "azure":
        azure_auth.reload_credential(db)
    if category in {"application", "kubernetes", "ai"}:
        invalidate_runtime_config()
    return {"category": category, "settings": saved, "message": "Settings saved."}


@router.post("/azure", summary="Save Azure connection settings")
def save_azure_settings(request: Request, body: AzureSettingsIn, db: Session = Depends(get_db)):
    require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "client_secret" in payload and payload["client_secret"] == "":
        payload.pop("client_secret")
    saved = save_category_settings(db, "azure", payload)
    azure_auth.reload_credential(db)
    return {"category": "azure", "settings": saved, "message": "Azure settings saved."}


@router.post("/database", summary="Save database connection settings")
def save_database_settings(request: Request, body: DatabaseSettingsIn, db: Session = Depends(get_db)):
    require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "password" in payload and payload["password"] == "":
        payload.pop("password")
    saved = save_category_settings(db, "database", payload)
    return {
        "category": "database",
        "settings": saved,
        "message": "Database settings saved. Click Apply connection to switch without restarting.",
        "connection_url": mask_database_url(build_database_url(get_system_config(db, "database"))),
    }


@router.post("/application", summary="Save application settings")
def save_application_settings(request: Request, body: ApplicationSettingsIn, db: Session = Depends(get_db)):
    require_admin_user(request)
    saved = save_category_settings(db, "application", body.model_dump(exclude_none=True))
    invalidate_runtime_config()
    return {
        "category": "application",
        "settings": saved,
        "message": "Application settings saved. CORS changes are active immediately.",
    }


@router.post("/kubernetes", summary="Save Kubernetes agent settings")
def save_kubernetes_settings(request: Request, body: KubernetesSettingsIn, db: Session = Depends(get_db)):
    require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "agent_token" in payload and payload["agent_token"] == "":
        payload.pop("agent_token")
    saved = save_category_settings(db, "kubernetes", payload)
    invalidate_runtime_config()
    return {"category": "kubernetes", "settings": saved, "message": "Kubernetes settings saved."}


@router.post("/ai", summary="Save Azure OpenAI settings for analysis enrichment")
def save_ai_settings(request: Request, body: AiSettingsIn, db: Session = Depends(get_db)):
    require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "openai_key" in payload and payload["openai_key"] == "":
        payload.pop("openai_key")
    saved = save_category_settings(db, "ai", payload)
    invalidate_runtime_config()
    return {"category": "ai", "settings": saved, "message": "AI settings saved."}


@router.post("/ai/test", summary="Test Azure OpenAI connection")
def test_ai_settings(
    request: Request,
    body: Optional[AiSettingsIn] = None,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    cfg = get_system_config(db, "ai")
    if body:
        updates = body.model_dump(exclude_none=True)
        if updates.get("openai_key") == "":
            updates.pop("openai_key", None)
        cfg.update(updates)
    result = verify_ai_connection(cfg, db=db)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message") or "AI connection test failed.")
    return result


@router.post("/azure/test", summary="Test Azure connection with provided or stored settings")
def test_azure_settings(
    request: Request,
    body: Optional[AzureSettingsIn] = None,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    config = get_system_config(db, "azure")
    if body:
        overrides = body.model_dump(exclude_none=True)
        if overrides.get("client_secret") == "":
            overrides.pop("client_secret", None)
        config.update(overrides)
    result = test_azure_connection(config)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message", "Azure connection failed"))
    return result


@router.post("/database/test", summary="Test database connection with provided or stored settings")
def test_database_settings(
    request: Request,
    body: Optional[DatabaseSettingsIn] = None,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    config = get_system_config(db, "database")
    if body:
        overrides = body.model_dump(exclude_none=True)
        if overrides.get("password") == "":
            overrides.pop("password", None)
        config.update(overrides)
    result = test_database_connection(config)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message", "Database connection failed"))
    return result


@router.post("/database/apply", summary="Apply stored database connection without restarting the API")
def apply_database_settings(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    try:
        result = apply_database_connection(db)
    except Exception as exc:
        raise HTTPException(400, f"Could not apply database connection: {exc}") from exc
    invalidate_runtime_config()
    return result


@router.post("/reload", summary="Reload Azure credentials from stored settings")
def reload_settings(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    azure_auth.reload_credential(db)
    return {"status": "ok", "message": "Azure credentials reloaded from database settings."}

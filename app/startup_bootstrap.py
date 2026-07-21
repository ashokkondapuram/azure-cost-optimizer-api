"""First-run bootstrap for Azure App Service deployments."""
from __future__ import annotations

import os
import structlog

from app.platform import get_app_service_database_url, is_azure_app_service

log = structlog.get_logger()


def bootstrap_app_service() -> None:
    """Configure managed identity + database when running on Azure Web App."""
    if not is_azure_app_service():
        return

    from app.database import SessionLocal, get_active_database_url, migrate_schema, reconfigure_engine
    from app import auth as azure_auth
    from app.models import SystemSetting
    from app.services.system_settings import save_category_settings

    db_url = get_app_service_database_url()
    if db_url and db_url != get_active_database_url():
        log.info("app_service_database_configure", url_masked=db_url.split("@")[-1] if "@" in db_url else "sqlite")
        reconfigure_engine(db_url)
        migrate_schema()

    db = SessionLocal()
    try:
        azure_row = db.query(SystemSetting).filter(SystemSetting.category == "azure").first()
        if not azure_row:
            payload = {
                "auth_mode": "managed_identity",
                "client_id": os.getenv("AZURE_CLIENT_ID", ""),
                "default_subscription_id": os.getenv("AZURE_DEFAULT_SUBSCRIPTION_ID", ""),
            }
            save_category_settings(db, "azure", payload)
            log.info("app_service_azure_settings_seeded", auth_mode="managed_identity")

        azure_auth.reload_credential(db)
    finally:
        db.close()

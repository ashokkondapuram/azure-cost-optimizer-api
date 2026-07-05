"""Azure platform detection (App Service, managed identity endpoint)."""
from __future__ import annotations

import os
import re
from urllib.parse import quote_plus


def is_azure_app_service() -> bool:
    return bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"))


def is_managed_identity_available() -> bool:
    return bool(
        os.getenv("IDENTITY_ENDPOINT")
        or os.getenv("MSI_ENDPOINT")
        or os.getenv("AZURE_CLIENT_ID")  # user-assigned MI on App Service
    )


def get_deployment_context() -> dict:
    on_app_service = is_azure_app_service()
    return {
        "is_app_service": on_app_service,
        "site_name": os.getenv("WEBSITE_SITE_NAME"),
        "resource_group": os.getenv("WEBSITE_RESOURCE_GROUP"),
        "managed_identity_available": is_managed_identity_available(),
        "recommended_azure_auth": "managed_identity" if on_app_service else None,
    }


def _parse_ado_net_connection_string(raw: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        parts[key.strip().lower()] = value.strip()
    return parts


def normalize_database_url(raw: str) -> str:
    """Convert App Service / Azure connection strings to SQLAlchemy URLs."""
    value = (raw or "").strip()
    if not value:
        return value
    if value.startswith(("postgresql://", "postgres://", "sqlite://")):
        return value

    parts = _parse_ado_net_connection_string(value)
    host = parts.get("server") or parts.get("host") or parts.get("data source") or ""
    host = host.replace("tcp:", "").split(",")[0].strip()
    database = parts.get("database") or parts.get("initial catalog") or ""
    user = parts.get("user id") or parts.get("uid") or parts.get("user") or ""
    password = parts.get("password") or parts.get("pwd") or ""
    port = parts.get("port") or "5432"

    # Strip @servername suffix from Azure PostgreSQL usernames when duplicated in host
    if "@" in user and host and user.split("@", 1)[1] in host:
        user = user.split("@", 1)[0]

    if not host or not database:
        return value

    auth = ""
    if user:
        auth = quote_plus(user)
        if password:
            auth = f"{auth}:{quote_plus(password)}"
        auth = f"{auth}@"

    url = f"postgresql://{auth}{host}:{port}/{quote_plus(database)}"
    ssl = (parts.get("ssl mode") or parts.get("sslmode") or "require").lower()
    if ssl and ssl != "disable":
        url += f"?sslmode={quote_plus(ssl)}"
    return url


def get_app_service_database_url() -> str | None:
    """Resolve database URL from App Service application settings / connection strings."""
    direct = os.getenv("DATABASE_URL")
    if direct:
        return normalize_database_url(direct)

    for key, value in os.environ.items():
        if not value:
            continue
        upper = key.upper()
        if upper.startswith("POSTGRESQLCONNSTR_") or upper.startswith("SQLCONNSTR_"):
            return normalize_database_url(value)
        if upper.startswith("CUSTOMCONNSTR_") and re.search(r"postgres|database", value, re.I):
            return normalize_database_url(value)

    return None

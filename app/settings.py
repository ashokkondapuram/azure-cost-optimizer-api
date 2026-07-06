"""Central application settings loaded from environment variables via Pydantic BaseSettings."""
from __future__ import annotations

from typing import List

try:
    from pydantic_settings import BaseSettings
    from pydantic import SecretStr, field_validator, model_validator
except ImportError:  # pragma: no cover
    raise RuntimeError(
        "pydantic-settings is required. Install it with: pip install pydantic-settings"
    )


class FeatureFlags(BaseSettings):
    """Per-environment feature toggles.  Set env-var FEATURE_<NAME>=false to disable."""
    feature_ai_enrichment: bool = True
    feature_cost_export: bool = True
    feature_advisor_sync: bool = True
    feature_anomaly_detection: bool = True
    feature_tag_compliance: bool = True
    feature_budget_alerts: bool = True
    feature_webhook_notifications: bool = True

    model_config = {"env_prefix": "", "case_sensitive": False}


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./azurefinops.db"
    cors_allowed_origins: List[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    request_timeout_seconds: int = 60

    # ── Auth ──────────────────────────────────────────────────────────────────
    auth_enabled: bool = True
    jwt_secret: SecretStr = SecretStr("")
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("")
    viewer_username: str = "viewer"
    viewer_password: SecretStr = SecretStr("")

    # ── Kubernetes agent ──────────────────────────────────────────────────────
    k8s_agent_token: SecretStr | None = None
    require_k8s_token: bool = False

    # ── Feature flags (nested) ────────────────────────────────────────────────
    features: FeatureFlags = FeatureFlags()

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        # Allows CORS_ALLOWED_ORIGINS="http://a.com,http://b.com" as comma-sep string
        "env_nested_delimiter": "__",
    }

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, v):
        return (v or "INFO").strip().upper()

    @field_validator("app_env", mode="before")
    @classmethod
    def _lower_app_env(cls, v):
        return (v or "development").strip().lower()

    @field_validator("admin_username", "viewer_username", mode="before")
    @classmethod
    def _lower_username(cls, v):
        return (v or "").strip().lower() or "admin"

    @property
    def is_production(self) -> bool:
        return self.app_env in {"prod", "production"}

    @property
    def jwt_configured(self) -> bool:
        return bool(self.jwt_secret.get_secret_value().strip())

    def validate_startup(self) -> None:
        if self.is_production and self.database_url.startswith("sqlite"):
            raise RuntimeError("DATABASE_URL must point to PostgreSQL in production")
        if self.is_production and not self.auth_enabled:
            raise RuntimeError("AUTH_ENABLED must not be false in production")
        if self.is_production and not self.jwt_configured:
            raise RuntimeError(
                "JWT_SECRET is required in production (set it in App Service application settings)"
            )
        if self.is_production and not (self.k8s_agent_token and self.k8s_agent_token.get_secret_value()):
            raise RuntimeError(
                "K8S_AGENT_TOKEN is required in production for /k8s agent routes"
            )
        if self.is_production and not self.admin_password.get_secret_value().strip():
            raise RuntimeError(
                "ADMIN_PASSWORD is required in production when bootstrapping the first admin user"
            )
        if self.require_k8s_token and not (
            self.k8s_agent_token and self.k8s_agent_token.get_secret_value()
        ):
            raise RuntimeError(
                "K8S_AGENT_TOKEN is required when REQUIRE_K8S_AGENT_TOKEN is enabled"
            )


# Module-level singleton — replaced by reset_settings() when hot-reload is needed.
_settings_instance: Settings | None = None
_settings_lock = __import__("threading").Lock()


def get_settings() -> Settings:
    """Return the cached Settings singleton, building it on first call."""
    global _settings_instance
    if _settings_instance is not None:
        return _settings_instance
    with _settings_lock:
        if _settings_instance is None:
            _settings_instance = Settings()
    return _settings_instance


def reset_settings() -> Settings:
    """Discard the cached singleton and rebuild from the current environment.

    Call this after writing new values to the database / environment so the
    next call to get_settings() picks up the fresh config.
    """
    global _settings_instance
    with _settings_lock:
        _settings_instance = None
    return get_settings()

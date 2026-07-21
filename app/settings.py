"""Central application settings loaded from environment variables via Pydantic BaseSettings."""
from __future__ import annotations

import functools
from typing import Annotated, List

try:
    from pydantic_settings import BaseSettings, NoDecode
    from pydantic import AliasChoices, Field, SecretStr, field_validator
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "pydantic-settings>=2.7.0 is required (NoDecode for CORS parsing). "
        "Install with: pip install 'pydantic-settings>=2.7.0'"
    ) from exc

_DEFAULT_CORS_ORIGINS = ["http://127.0.0.1:3000", "http://localhost:3000"]


class FeatureFlags(BaseSettings):
    """Per-environment feature toggles.  Set env-var FEATURE_<NAME>=false to disable."""
    feature_cost_export: bool = True
    feature_advisor_sync: bool = True
    feature_anomaly_detection: bool = True

    model_config = {"env_prefix": "", "case_sensitive": False}


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./azurefinops.db"
    # NoDecode: pydantic-settings JSON-decodes List env vars before validators; "" crashes.
    cors_allowed_origins: Annotated[List[str], NoDecode] = list(_DEFAULT_CORS_ORIGINS)
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

    # ── Database pool (PostgreSQL only) ───────────────────────────────────────
    # Six platform microservices share one Postgres. Defaults: 8 + 12 overflow = 20/service
    # (≈120 across 6 services). Set POSTGRES max_connections ≥ 200 in Docker/production.
    database_pool_size: int = Field(
        default=8,
        validation_alias=AliasChoices("DATABASE_POOL_SIZE", "database_pool_size"),
    )
    database_max_overflow: int = Field(
        default=12,
        validation_alias=AliasChoices("DATABASE_MAX_OVERFLOW", "database_max_overflow"),
    )
    database_pool_timeout_sec: float = Field(
        default=30.0,
        validation_alias=AliasChoices("DATABASE_POOL_TIMEOUT_SEC", "database_pool_timeout_sec"),
    )
    database_pool_recycle_sec: int = Field(
        default=1800,
        validation_alias=AliasChoices("DATABASE_POOL_RECYCLE_SEC", "database_pool_recycle_sec"),
    )

    # ── Auth session / cache ──────────────────────────────────────────────────
    auth_user_cache_seconds: int = 60
    session_idle_minutes: int = 1
    jwt_expire_hours: int | None = None
    jwt_expire_minutes: int | None = None

    # ── Resource enrichment freshness ─────────────────────────────────────────
    enrichment_max_age_hours: float = 6.0

    # ── Background metrics sync worker ────────────────────────────────────────
    metrics_sync_interval_hours: float = 0.5  # legacy hours alias; see METRICS_SYNC_INTERVAL_MINUTES
    metrics_sync_startup_delay_sec: float = 120.0
    metrics_sync_worker_enabled: bool = True

    # ── Azure Monitor metrics fetch (analysis / inventory) ────────────────────
    analysis_monitor_metrics_timespan: str = Field(
        default="P7D",
        validation_alias=AliasChoices(
            "ANALYSIS_MONITOR_METRICS_TIMESPAN",
            "ANALYSIS_VM_METRICS_TIMESPAN",
        ),
    )
    analysis_monitor_metrics_limit_per_type: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "ANALYSIS_MONITOR_METRICS_LIMIT_PER_TYPE",
            "ANALYSIS_VM_METRICS_LIMIT",
        ),
    )
    analysis_monitor_metrics_workers: int = 6
    analysis_monitor_metrics_timeout_sec: int = Field(
        default=120,
        validation_alias=AliasChoices(
            "ANALYSIS_MONITOR_METRICS_TIMEOUT_SEC",
            "ANALYSIS_VM_METRICS_TIMEOUT_SEC",
        ),
    )

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
            stripped = v.strip()
            if not stripped:
                return list(_DEFAULT_CORS_ORIGINS)
            if stripped.startswith("["):
                import json

                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [o.strip() for o in stripped.split(",") if o.strip()]
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

    @field_validator("database_pool_size", mode="after")
    @classmethod
    def _clamp_pool_size(cls, v: int) -> int:
        return max(1, v)

    @field_validator("database_max_overflow", mode="after")
    @classmethod
    def _clamp_max_overflow(cls, v: int) -> int:
        return max(0, v)

    @field_validator("database_pool_timeout_sec", mode="after")
    @classmethod
    def _clamp_pool_timeout(cls, v: float) -> float:
        return max(1.0, float(v))

    @field_validator("database_pool_recycle_sec", mode="after")
    @classmethod
    def _clamp_pool_recycle(cls, v: int) -> int:
        return max(60, int(v))

    @field_validator("auth_user_cache_seconds", mode="after")
    @classmethod
    def _clamp_auth_cache(cls, v: int) -> int:
        return max(0, v)

    @field_validator("session_idle_minutes", mode="after")
    @classmethod
    def _clamp_session_idle(cls, v: int) -> int:
        return max(1, v)

    @field_validator("enrichment_max_age_hours", mode="after")
    @classmethod
    def _clamp_enrichment_age(cls, v: float) -> float:
        return max(0.25, float(v))

    @field_validator("metrics_sync_interval_hours", mode="after")
    @classmethod
    def _clamp_metrics_sync_interval(cls, v: float) -> float:
        return max(1.0 / 60.0, float(v))

    @field_validator("metrics_sync_startup_delay_sec", mode="after")
    @classmethod
    def _clamp_metrics_sync_delay(cls, v: float) -> float:
        return max(0.0, float(v))

    @field_validator("analysis_monitor_metrics_workers", mode="after")
    @classmethod
    def _clamp_monitor_workers(cls, v: int) -> int:
        return max(1, min(8, v))

    @field_validator("analysis_monitor_metrics_timeout_sec", mode="after")
    @classmethod
    def _clamp_monitor_timeout(cls, v: int) -> int:
        return max(5, v)

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


@functools.lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton, building it on first call."""
    return Settings()


def reset_settings() -> Settings:
    """Discard the cached singleton and rebuild from the current environment.

    Call this after writing new values to the database / environment so the
    next call to get_settings() picks up the fresh config.
    """
    get_settings.cache_clear()
    return get_settings()

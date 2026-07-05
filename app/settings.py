"""Central application settings loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


@lru_cache
def get_settings():
    class Settings:
        app_env: str = os.getenv('APP_ENV', 'development').strip().lower()
        log_level: str = os.getenv('LOG_LEVEL', 'INFO').strip().upper()
        database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./azurefinops.db')
        cors_allowed_origins: list[str] = [
            o.strip()
            for o in os.getenv(
                'CORS_ALLOWED_ORIGINS',
                'http://127.0.0.1:3000,http://localhost:3000',
            ).split(',')
            if o.strip()
        ]
        request_timeout_seconds: int = int(os.getenv('REQUEST_TIMEOUT_SECONDS', '60'))
        k8s_agent_token: str | None = os.getenv('K8S_AGENT_TOKEN') or None
        require_k8s_token: bool = _env_bool('REQUIRE_K8S_AGENT_TOKEN', False)
        auth_enabled: bool = _env_bool('AUTH_ENABLED', True)
        jwt_secret: str = os.getenv('JWT_SECRET', '').strip()
        admin_username: str = os.getenv('ADMIN_USERNAME', 'admin').strip().lower() or 'admin'
        admin_password: str = os.getenv('ADMIN_PASSWORD', '').strip()
        viewer_username: str = os.getenv('VIEWER_USERNAME', 'viewer').strip().lower() or 'viewer'
        viewer_password: str = os.getenv('VIEWER_PASSWORD', '').strip()

        @property
        def is_production(self) -> bool:
            return self.app_env in {'prod', 'production'}

        @property
        def jwt_configured(self) -> bool:
            return bool((os.getenv('JWT_SECRET') or self.jwt_secret or '').strip())

        def validate_startup(self) -> None:
            if self.is_production and self.database_url.startswith('sqlite'):
                raise RuntimeError('DATABASE_URL must point to PostgreSQL in production')
            if self.is_production and not self.auth_enabled:
                raise RuntimeError('AUTH_ENABLED must not be false in production')
            if self.is_production and not self.jwt_configured:
                raise RuntimeError(
                    'JWT_SECRET is required in production (set it in App Service application settings)',
                )
            # K8s agent: require token in production unless explicitly disabled for dev-like prod.
            if self.is_production and not self.k8s_agent_token:
                raise RuntimeError(
                    'K8S_AGENT_TOKEN is required in production for /k8s agent routes',
                )
            if self.is_production and not (self.admin_password or '').strip():
                raise RuntimeError(
                    'ADMIN_PASSWORD is required in production when bootstrapping the first admin user',
                )
            if self.require_k8s_token and not self.k8s_agent_token:
                raise RuntimeError(
                    'K8S_AGENT_TOKEN is required when REQUIRE_K8S_AGENT_TOKEN is enabled',
                )

    return Settings()

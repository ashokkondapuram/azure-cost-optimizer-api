"""Setting category definitions and defaults."""

SETTING_CATEGORIES = ("azure", "database", "application", "kubernetes", "ai")

SECRET_KEYS = {
    "azure": {"client_secret"},
    "database": {"password"},
    "application": set(),
    "kubernetes": {"agent_token"},
    "ai": {"openai_key"},
}

SETTING_DEFAULTS = {
    "azure": {
        "auth_mode": "managed_identity",
        "tenant_id": "",
        "client_id": "",
        "client_secret": "",
        "default_subscription_id": "",
    },
    "database": {
        "dialect": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database": "azure_cost_db",
        "username": "",
        "password": "",
        "ssl_mode": "prefer",
    },
    "application": {
        "app_env": "development",
        "cors_allowed_origins": "http://127.0.0.1:3000,http://localhost:3000",
        "request_timeout_seconds": 60,
        "log_level": "INFO",
    },
    "kubernetes": {
        "agent_token": "",
        "require_agent_token": False,
    },
    "ai": {
        "ai_enabled": True,
        "ai_auth_mode": "api_key",
        "openai_key": "",
        "openai_endpoint": "",
        "openai_deployment": "",
        "openai_api_version": "2024-08-01-preview",
        "ai_enrich_all_findings": True,
        "ai_max_findings_per_run": 200,
        "ai_batch_size": 10,
    },
}

ENV_KEY_MAP = {
    "azure": {
        "auth_mode": "AZURE_AUTH_MODE",
        "tenant_id": "AZURE_TENANT_ID",
        "client_id": "AZURE_CLIENT_ID",
        "client_secret": "AZURE_CLIENT_SECRET",
        "default_subscription_id": "AZURE_DEFAULT_SUBSCRIPTION_ID",
    },
    "database": {
        "host": "DB_HOST",
        "port": "DB_PORT",
        "database": "DB_NAME",
        "username": "DB_USER",
        "password": "DB_PASSWORD",
        "ssl_mode": "DB_SSL_MODE",
    },
    "application": {
        "app_env": "APP_ENV",
        "cors_allowed_origins": "CORS_ALLOWED_ORIGINS",
        "request_timeout_seconds": "REQUEST_TIMEOUT_SECONDS",
        "log_level": "LOG_LEVEL",
    },
    "kubernetes": {
        "agent_token": "K8S_AGENT_TOKEN",
        "require_agent_token": "REQUIRE_K8S_AGENT_TOKEN",
    },
    "ai": {
        "ai_enabled": "AI_ENABLED",
        "ai_auth_mode": "AI_AUTH_MODE",
        "openai_key": "OPENAI_KEY",
        "openai_endpoint": "OPENAI_ENDPOINT",
        "openai_deployment": "OPENAI_DEPLOYMENT",
        "openai_api_version": "OPENAI_API_VERSION",
        "ai_enrich_all_findings": "AI_ENRICH_ALL_FINDINGS",
        "ai_max_findings_per_run": "AI_MAX_FINDINGS_PER_RUN",
        "ai_batch_size": "AI_BATCH_SIZE",
    },
}

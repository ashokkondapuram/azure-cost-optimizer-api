"""Setting category definitions and defaults."""

SETTING_CATEGORIES = ("azure", "database", "application", "kubernetes")

SECRET_KEYS = {
    "azure": {"client_secret"},
    "database": {"password"},
    "application": set(),
    "kubernetes": {"agent_token"},
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
        "agent_api_url": "",
        "agent_image": "",
        "poll_interval_seconds": 60,
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
        "agent_api_url": "K8S_AGENT_API_URL",
        "agent_image": "K8S_AGENT_IMAGE",
        "poll_interval_seconds": "K8S_AGENT_POLL_INTERVAL",
    },
}

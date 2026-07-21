"""Tests for AI settings category schema and persistence."""

from app.database import SessionLocal, init_db
from app.services.settings_schema import (
    ENV_KEY_MAP,
    SECRET_KEYS,
    SETTING_CATEGORIES,
    SETTING_DEFAULTS,
)
from app.services.system_settings import get_category_settings, save_category_settings


def test_ai_category_registered():
    assert "ai" in SETTING_CATEGORIES
    assert "openai_key" in SECRET_KEYS["ai"]
    assert SETTING_DEFAULTS["ai"]["ai_enabled"] is True
    assert SETTING_DEFAULTS["ai"]["openai_api_version"]
    assert ENV_KEY_MAP["ai"]["openai_key"] == "OPENAI_KEY"
    assert ENV_KEY_MAP["ai"]["openai_endpoint"] == "OPENAI_ENDPOINT"


def test_save_and_load_ai_settings_masked():
    init_db()
    db = SessionLocal()
    try:
        saved = save_category_settings(db, "ai", {
            "ai_enabled": True,
            "openai_endpoint": "https://test.openai.azure.com",
            "openai_deployment": "gpt-4o-mini",
            "openai_api_version": "2024-08-01-preview",
            "openai_key": "super-secret-key",
            "ai_max_findings_per_run": 30,
        })
        assert saved["ai_enabled"] is True
        assert saved["openai_key_set"] is True
        assert "super-secret" not in str(saved.get("openai_key", ""))

        loaded = get_category_settings(db, "ai", masked=False)
        assert loaded["openai_endpoint"] == "https://test.openai.azure.com"
        assert loaded["openai_key"] == "super-secret-key"
        assert loaded["ai_max_findings_per_run"] == 30
    finally:
        db.close()

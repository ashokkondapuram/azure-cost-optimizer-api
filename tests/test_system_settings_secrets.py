"""Effective settings merge when encrypted DB secrets are stale."""
import json
import uuid

import pytest
from cryptography.fernet import Fernet

from app.database import SessionLocal, init_db
from app.models import SystemSetting
from app.services.system_settings import get_effective_config


def test_openai_key_falls_back_to_env_when_db_secret_stale(monkeypatch):
    init_db()
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("JWT_SECRET", "jwt-for-settings-test")
    monkeypatch.setenv("OPENAI_KEY", "env-openai-key-from-app-settings")

    other_key = Fernet.generate_key()
    f = Fernet(other_key)
    stale = "enc:" + f.encrypt(b"old-db-key").decode()

    db = SessionLocal()
    try:
        db.query(SystemSetting).filter(SystemSetting.category == "ai").delete()
        db.commit()
        db.add(
            SystemSetting(
                id=str(uuid.uuid4()),
                category="ai",
                config_json=json.dumps({"openai_key": stale}),
            )
        )
        db.commit()
        cfg = get_effective_config(db, "ai")
        assert cfg["openai_key"] == "env-openai-key-from-app-settings"
    finally:
        db.close()

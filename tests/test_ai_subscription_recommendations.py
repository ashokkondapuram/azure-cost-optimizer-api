"""Tests for subscription-level AI recommendations."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_subscription_recommendations import generate_subscription_ai_recommendations
from app.models import Base, OptimizationFinding


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _ai_config():
    return {
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "openai_api_version": "2024-08-01-preview",
        "ai_max_findings_per_run": 40,
        "ai_enrich_all_findings": True,
        "ai_batch_size": 10,
    }


def _add_finding(db_session, sub: str, *, rule_id: str, savings: float, name: str):
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        rule_id=rule_id,
        rule_name=rule_id,
        category="COMPUTE",
        severity="HIGH",
        resource_id=f"/subscriptions/{sub}/resourcegroups/rg/providers/microsoft.compute/disks/{name}",
        resource_name=name,
        resource_type="Microsoft.Compute/disks",
        resource_group="rg",
        detail="Unused disk",
        recommendation="Delete disk",
        estimated_savings_usd=savings,
        status="open",
        detected_at=datetime.now(timezone.utc),
        evidence_json=json.dumps({"age_days": 45, "disk_state": "unattached"}),
    ))


@patch("app.ai_subscription_recommendations._load_ai_config", return_value=None)
def test_ai_recommendations_not_configured(mock_cfg, db_session):
    out = generate_subscription_ai_recommendations(db_session, "sub-1")
    assert out["ai_context"]["status"] == "not_configured"
    assert out["recommendations"] == []


@patch("app.ai_subscription_recommendations._load_ai_config")
def test_ai_recommendations_no_findings(mock_cfg, db_session):
    mock_cfg.return_value = _ai_config()
    out = generate_subscription_ai_recommendations(db_session, "sub-1")
    assert out["ai_context"]["status"] == "no_data"
    assert out["findings_analyzed"] == 0


@patch("app.ai_subscription_recommendations.chat_completion")
@patch("app.ai_subscription_recommendations._load_ai_config")
@patch("app.ai_subscription_recommendations._subscription_context")
def test_ai_recommendations_returns_model_output(mock_ctx, mock_cfg, mock_chat, db_session):
    sub = "sub-1"
    mock_cfg.return_value = _ai_config()
    mock_ctx.return_value = {"month": "2026-07", "open_findings": 2}
    _add_finding(db_session, sub, rule_id="DISK_UNUSED", savings=120, name="disk-a")
    _add_finding(db_session, sub, rule_id="DISK_UNUSED", savings=80, name="disk-b")
    db_session.commit()

    mock_chat.return_value = json.dumps({
        "executive_summary": "Two idle disks drive most waste.",
        "total_estimated_monthly_savings_usd": 200,
        "quick_wins": ["Delete unattached disks after backup validation"],
        "data_gaps": [],
        "recommendations": [
            {
                "priority": 1,
                "title": "Remove idle managed disks",
                "category": "storage",
                "recommendation": "Delete both unattached disks in rg.",
                "rationale": "Both disks are unattached for 45 days.",
                "estimated_monthly_savings_usd": 200,
                "risk_level": "medium",
                "confidence": "high",
                "implementation_steps": ["Validate backups", "Delete disks"],
                "related_rule_ids": ["DISK_UNUSED"],
                "related_resources": ["disk-a", "disk-b"],
            },
        ],
    })

    out = generate_subscription_ai_recommendations(db_session, sub, force_refresh=True)

    assert out["ai_context"]["status"] == "completed"
    assert out["findings_analyzed"] == 2
    assert out["executive_summary"] == "Two idle disks drive most waste."
    assert len(out["recommendations"]) == 1
    assert out["recommendations"][0]["title"] == "Remove idle managed disks"
    assert out["quick_wins"][0].startswith("Delete unattached")
    mock_chat.assert_called_once()


@patch("app.ai_subscription_recommendations.chat_completion", return_value=None)
@patch("app.ai_subscription_recommendations._load_ai_config")
@patch("app.ai_subscription_recommendations._subscription_context")
def test_ai_recommendations_failed_on_empty_model_response(mock_ctx, mock_cfg, mock_chat, db_session):
    sub = "sub-1"
    mock_cfg.return_value = _ai_config()
    mock_ctx.return_value = {}
    _add_finding(db_session, sub, rule_id="VM_IDLE", savings=50, name="vm-a")
    db_session.commit()

    out = generate_subscription_ai_recommendations(db_session, sub, force_refresh=True)
    assert out["ai_context"]["status"] == "failed"
    assert out["recommendations"] == []

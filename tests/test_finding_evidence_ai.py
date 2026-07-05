"""Tests for AI enrichment preservation in evidence payloads."""
from __future__ import annotations

from app.finding_evidence import enrich_evidence


def test_enrich_evidence_preserves_ai_insight():
    ai_block = {
        "executive_summary": "High spend on underutilized gateway.",
        "recommendation": "Review SKU and backend pool utilization.",
        "implementation_steps": ["Check metrics", "Rightsize SKU"],
        "risk_level": "medium",
        "provider": "azure_openai",
    }
    rule_engine = {
        "recommendation": "Review usage and confirm ownership.",
        "detail": "MTD spend exceeds threshold.",
    }
    raw = {
        "monthly_cost_usd": 4667.0,
        "summary": "MTD spend $4,667",
        "ai_insight": ai_block,
        "rule_engine": rule_engine,
        "data_source": "cost_export",
    }
    finding = {
        "rule_id": "COST_HIGH_SPEND_REVIEW",
        "detail": "High spend on underutilized gateway.",
        "recommendation": "Review SKU and backend pool utilization.",
        "estimated_savings_usd": 778.0,
        "resource_type": "network/appgateway",
    }

    enriched = enrich_evidence("COST_HIGH_SPEND_REVIEW", raw, finding)

    assert enriched.get("ai_insight") == ai_block
    assert enriched.get("rule_engine") == rule_engine
    assert enriched.get("checks")
    assert enriched.get("summary")

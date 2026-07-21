"""Tests for Azure OpenAI analysis enrichment."""

import json
from unittest.mock import patch

from app.ai_analysis import enrich_analysis_with_ai
from app.ai_client import build_ai_config


def test_build_ai_config_requires_enabled_and_credentials():
    assert build_ai_config({"ai_enabled": False, "openai_key": "x"}) is None
    assert build_ai_config({
        "ai_enabled": True,
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
    }) is not None


@patch("app.ai_analysis.chat_completion")
def test_enrich_analysis_with_ai_applies_model_output(mock_chat):
    mock_chat.return_value = json.dumps({
        "enrichments": [
            {
                "index": 0,
                "executive_summary": "Disk has been idle for weeks.",
                "recommendation": "Delete after validating backups.",
                "implementation_steps": ["Confirm no restore dependency", "Delete disk"],
                "risk_level": "medium",
                "confidence_delta": 5,
                "stale_likelihood": "high",
            },
        ],
    })
    result = {
        "findings": [
            {
                "rule_id": "DISK_UNUSED_EXTENDED",
                "detail": "Disk is unattached.",
                "recommendation": "Delete disk.",
                "estimated_savings_usd": 120,
                "confidence_score": 80,
                "evidence": {"age_days": 30},
            },
        ],
    }
    config = {
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "openai_api_version": "2024-08-01-preview",
        "ai_max_findings_per_run": 40,
        "ai_enrich_all_findings": False,
    }
    enriched = enrich_analysis_with_ai(None, result, config=config)
    finding = enriched["findings"][0]
    assert enriched["ai_context"]["enriched_count"] == 1
    assert finding["recommendation"] == "Delete after validating backups."
    assert finding["recommendation_source"] == "ai"
    assert finding["detail"] == "Disk has been idle for weeks."
    assert finding["evidence"]["ai_insight"]["risk_level"] == "medium"
    assert finding["evidence"]["rule_engine"]["recommendation"] == "Delete disk."
    assert finding["confidence_score"] == 85


@patch("app.ai_analysis.chat_completion", return_value=None)
def test_enrich_analysis_with_ai_noop_on_failure(mock_chat):
    result = {"findings": [{"rule_id": "X", "estimated_savings_usd": 1}]}
    config = {
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "openai_api_version": "2024-08-01-preview",
        "ai_max_findings_per_run": 40,
        "ai_enrich_all_findings": False,
    }
    out = enrich_analysis_with_ai(None, result, config=config)
    assert out["findings"][0]["rule_id"] == "X"
    assert out["ai_context"]["status"] == "failed"


@patch("app.ai_analysis.chat_completion")
def test_enrich_selects_top_savings_findings_only(mock_chat):
    mock_chat.return_value = json.dumps({"enrichments": []})
    findings = [
        {"rule_id": "LOW", "estimated_savings_usd": 5, "evidence": {}},
        {"rule_id": "HIGH", "estimated_savings_usd": 500, "evidence": {}},
        {"rule_id": "MID", "estimated_savings_usd": 50, "evidence": {}},
    ]
    config = {
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "openai_api_version": "2024-08-01-preview",
        "ai_max_findings_per_run": 1,
        "ai_enrich_all_findings": False,
    }
    enrich_analysis_with_ai(None, {"findings": findings}, config=config)
    user_message = mock_chat.call_args[0][1][1]["content"]
    json_text = user_message.split("\n", 1)[1]
    payload = json.loads(json_text)
    sent = payload["findings"]
    assert len(sent) == 1
    assert sent[0]["rule"] == "HIGH"


def test_enrich_reports_not_configured_when_no_credentials():
    result = {"findings": [{"rule_id": "X", "estimated_savings_usd": 1}]}
    out = enrich_analysis_with_ai(None, result, config=None)
    assert out["ai_context"]["status"] == "not_configured"


def test_enrich_skips_when_include_ai_false():
    config = {
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "ai_max_findings_per_run": 40,
        "ai_enrich_all_findings": False,
    }
    result = {"findings": [{"rule_id": "X", "estimated_savings_usd": 1}]}
    out = enrich_analysis_with_ai(None, result, config=config, include_ai=False)
    assert "ai_context" not in out


@patch("app.ai_analysis.chat_completion")
def test_compact_finding_includes_metrics_and_checks(mock_chat):
    mock_chat.return_value = json.dumps({"enrichments": []})
    finding = {
        "rule_id": "VM_IDLE",
        "estimated_savings_usd": 200,
        "evidence": {
            "determination": "underutilized_cpu",
            "summary": "Low CPU",
            "avg_cpu_pct": 4.2,
            "checks": [{"signal": "CPU", "value": 4.2, "threshold": "< 5%", "passed": False}],
            "optimization_metrics": {
                "data_quality": "azure_monitor_and_cost",
                "performance": [{"id": "avg_cpu", "label": "Average CPU", "formatted": "4.2%", "status": "underutilized"}],
                "cost": [{"id": "mtd_cost", "label": "Month-to-date cost", "formatted": "$120.00"}],
            },
        },
    }
    config = {
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "ai_max_findings_per_run": 40,
        "ai_enrich_all_findings": False,
    }
    enrich_analysis_with_ai(None, {"findings": [finding]}, config=config)
    payload = json.loads(mock_chat.call_args[0][1][1]["content"].split("\n", 1)[1])
    sent = payload["findings"][0]
    assert sent["determination"] == "underutilized_cpu"
    assert sent["checks"][0].startswith("CPU:")
    assert sent["metrics"][0].startswith("avg_cpu=")


def test_parse_json_response_strips_markdown_fence():
    from app.ai_analysis import _parse_json_response
    parsed = _parse_json_response('```json\n{"enrichments": []}\n```')
    assert parsed == {"enrichments": []}


@patch("app.ai_analysis.chat_completion")
def test_enrich_batches_findings_to_reduce_tokens(mock_chat):
    def _side_effect(cfg, messages, **kwargs):
        body = json.loads(messages[1]["content"].split("\n", 1)[1])
        enrichments = []
        for row in body["findings"]:
            enrichments.append({
                "index": row["index"],
                "executive_summary": f"Summary {row['index']}",
                "recommendation": f"Action {row['index']}",
                "risk_level": "low",
            })
        return json.dumps({"enrichments": enrichments})

    mock_chat.side_effect = _side_effect
    findings = [
        {"rule_id": f"RULE_{i}", "estimated_savings_usd": 100 - i, "evidence": {}}
        for i in range(5)
    ]
    config = {
        "openai_key": "key",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "ai_max_findings_per_run": 10,
        "ai_enrich_all_findings": True,
        "ai_batch_size": 2,
    }
    out = enrich_analysis_with_ai(None, {"findings": findings}, config=config)
    assert mock_chat.call_count == 3
    assert out["ai_context"]["batch_count"] == 3
    assert out["ai_context"]["batch_size"] == 2
    assert out["ai_context"]["enriched_count"] == 5
    assert out["findings"][0]["recommendation_source"] == "ai"

"""Unit tests for API throttle helpers (rate limiter, envelope, cost client)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.messaging.api_throttle.config import kafka_api_throttle_enabled
from app.messaging.api_throttle.envelope import ApiDomain, ApiJobEnvelope, ApiJobStatus
from app.messaging.api_throttle.rate_limiter import DomainRateLimiter, reset_limiters, reset_rate_limiters
from app.messaging.api_throttle.topics import TOPIC_API_COST_REQUESTED, requested_topic_for_domain

SUBSCRIPTION_ID = str(uuid.uuid4()).lower()
PIPELINE_ID = str(uuid.uuid4())


def test_api_job_envelope_roundtrip():
    envelope = ApiJobEnvelope.create(
        domain=ApiDomain.COST_MANAGEMENT,
        operation="query_subscription_totals",
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        phase="subscription_totals",
        params={"timeframe": "MonthToDate"},
    )
    restored = ApiJobEnvelope.from_json(envelope.to_json())
    assert restored.job_id == envelope.job_id
    assert restored.domain == ApiDomain.COST_MANAGEMENT
    assert restored.idempotency_key == f"{PIPELINE_ID}:cost_management:query_subscription_totals"


def test_topic_mapping():
    assert requested_topic_for_domain(ApiDomain.COST_MANAGEMENT) == TOPIC_API_COST_REQUESTED
    assert requested_topic_for_domain(ApiDomain.MONITOR) == "api.metrics.requested"
    assert requested_topic_for_domain(ApiDomain.RESOURCE_GRAPH) == "api.inventory.requested"


def test_rate_limiter_adaptive_multiplier():
    reset_limiters()
    reset_rate_limiters()
    limiter = DomainRateLimiter(ApiDomain.COST_MANAGEMENT)
    assert limiter.adaptive_multiplier == 1.0
    limiter.record_429()
    assert limiter.adaptive_multiplier == 1.5
    limiter.record_success()
    assert limiter.adaptive_multiplier == 1.35


@patch("app.messaging.api_throttle.coordinator.enqueue_single_cost_phase")
def test_cost_client_routes_through_kafka(mock_enqueue, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_API_THROTTLE_ENABLED", "true")
    mock_enqueue.return_value = {"pretax_total": 1.0}

    from app.messaging.api_throttle.cost_client import cost_client_for_sync

    client = cost_client_for_sync(
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        token="test-token",
    )
    result = client.query_subscription_totals(SUBSCRIPTION_ID)
    assert result["pretax_total"] == 1.0
    mock_enqueue.assert_called_once()


def test_cost_client_inline_when_disabled(monkeypatch):
    monkeypatch.setenv("KAFKA_API_THROTTLE_ENABLED", "false")
    from app.messaging.api_throttle.cost_client import cost_client_for_sync
    from app.azure_cost import AzureCostClient

    client = cost_client_for_sync(
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
    )
    assert isinstance(client, AzureCostClient)


def test_kafka_api_throttle_enabled_requires_microservices(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_API_THROTTLE_ENABLED", "true")
    monkeypatch.delenv("MICROSERVICES_ONLY", raising=False)
    assert kafka_api_throttle_enabled() is False

    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    assert kafka_api_throttle_enabled() is True

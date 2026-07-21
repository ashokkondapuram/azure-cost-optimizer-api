"""Snapshot ingestion mirrors node metrics into K8sUtilization."""
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.integration_app import app
from app.models import K8sUtilization


def test_snapshot_syncs_utilization_rows(monkeypatch):
    monkeypatch.setenv("K8S_AGENT_TOKEN", "test-agent-token")
    init_db()
    client = TestClient(app)

    payload = {
        "cluster_name": "test-aks",
        "summary": {"node_count": 1, "pod_count": 2},
        "nodes": [
            {"name": "aks-nodepool1-abc123", "cpu_utilization_pct": 12.5, "memory_utilization_pct": 44.0},
        ],
        "pods": [],
    }
    resp = client.post(
        "/api/k8s/snapshot",
        json=payload,
        headers={"X-API-Key": "test-agent-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["utilization_rows"] == 1

    db = SessionLocal()
    try:
        rows = (
            db.query(K8sUtilization)
            .filter(K8sUtilization.cluster_name == "test-aks")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].node_name == "aks-nodepool1-abc123"
        assert rows[0].cpu_usage == "12.5%"
        assert rows[0].memory_usage == "44.0%"
    finally:
        db.close()

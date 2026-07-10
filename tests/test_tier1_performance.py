"""Tier 1 performance tests — inventory SQL filters and AKS indexing."""

import json
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ResourceSnapshot
from app.optimizer.engine import _index_aks_node_metrics
from app.resource_store import list_all_resources_db


def _memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_list_all_resources_db_excludes_do_not_optimize_tag():
    db = _memory_db()
    sub = "sub-1"
    for name, tags in (("keep", {}), ("skip", {"doNotOptimize": "true"})):
        db.add(ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            resource_id=f"/subscriptions/{sub}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/{name}",
            resource_name=name,
            resource_type="compute/vm",
            resource_group="rg",
            is_active=True,
            tags_json=json.dumps(tags),
        ))
    db.commit()

    rows = list_all_resources_db(db, sub)
    names = {r["name"] for r in rows}
    assert names == {"keep"}


def test_index_aks_node_metrics_uses_cluster_scoped_prefixes():
    clusters = [{"id": "/subscriptions/s/rg/c1", "name": "prod-aks", "properties": {}}]
    node_pools = {
        "/subscriptions/s/rg/c1": [{"name": "default"}],
    }
    node_metrics = {
        "prod-aks/aks-default-12345": {"value": []},
        "aks-otherpool-99999": {"value": []},
        "other-cluster/aks-default-777": {"value": []},
    }
    index = _index_aks_node_metrics(node_metrics, clusters, node_pools)
    assert len(index["prod-aks-default"]) == 1
    assert index["prod-aks-default"][0][0] == "prod-aks/aks-default-12345"
    assert index.get("prod-aks-otherpool", []) == []


def test_engine_config_cache_avoids_repeat_db_reads():
    from unittest.mock import MagicMock

    from app.optimizer.engine_config import (
        _config_cache,
        get_effective_config,
        invalidate_engine_config_cache,
    )

    invalidate_engine_config_cache()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    get_effective_config(db, "default")
    get_effective_config(db, "default")
    assert db.query.call_count == 1
    invalidate_engine_config_cache()

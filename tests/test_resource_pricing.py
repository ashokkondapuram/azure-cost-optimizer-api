"""Tests for per-resource SKU and pricing model resolution."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import migrate_schema
from app.db_sync import _upsert_resource
from app.models import Base, ResourcePricingProfile
from app.resource_pricing import (
    list_pricing_profiles_db,
    resolve_resource_pricing_profile,
    sku_pricing_table_rows,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migrate_schema()
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RID = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.ContainerRegistry/registries/acr1"


def test_resolve_acr_basic_free_tier():
    profile = resolve_resource_pricing_profile(
        canonical_type="containers/acr",
        sku_label="Basic",
        sku_json={"name": "Basic", "tier": "Basic"},
    )
    assert profile["sku_tier"] == "Basic"
    assert profile["pricing_model"] == "free_tier_limited"
    assert profile["cost_type"] == "conditional"
    assert profile["free_tier"]["duration"] == "always"
    assert profile["free_tier"]["limit"] == "10 GB storage"


def test_resolve_acr_premium_pay_as_you_go():
    profile = resolve_resource_pricing_profile(
        canonical_type="containers/acr",
        sku_label="Premium",
    )
    assert profile["pricing_model"] == "pay_as_you_go"
    assert profile["cost_type"] == "costed"


def test_resolve_keyvault_standard_hybrid():
    profile = resolve_resource_pricing_profile(
        canonical_type="security/keyvault",
        sku_label="standard",
    )
    assert profile["pricing_model"] == "hybrid"
    assert profile["free_tier"]["limit"] == "10,000 secret transactions/month"


def test_resolve_nsg_always_free():
    profile = resolve_resource_pricing_profile(
        canonical_type="network/nsg",
        sku_label=None,
    )
    assert profile["pricing_model"] == "always_free"
    assert profile["cost_type"] == "free"


def test_sku_pricing_table_has_entries():
    rows = sku_pricing_table_rows()
    assert any(r["canonical_type"] == "containers/acr" and r["sku"] == "Basic" for r in rows)
    assert any(r["canonical_type"] == "storage/account" for r in rows)


def test_upsert_resource_writes_pricing_profile(db):
    _upsert_resource(
        db,
        SUB,
        resource_id=RID,
        resource_name="acr1",
        resource_type="containers/acr",
        sku="Basic",
        sku_json={"name": "Basic", "tier": "Basic"},
    )
    db.commit()

    rows = db.query(ResourcePricingProfile).all()
    assert len(rows) == 1
    assert rows[0].sku_tier == "Basic"
    assert rows[0].pricing_model == "free_tier_limited"
    assert rows[0].service_name == "Container Registry"

    listed = list_pricing_profiles_db(db, SUB)
    assert listed["total"] == 1
    assert listed["items"][0]["pricing_model"] == "free_tier_limited"
    assert listed["items"][0]["free_tier"]["duration"] == "always"


def test_upsert_pricing_profile_dedupes_privatelinkservice_repeats():
    """Private link service sync must not insert duplicate pricing profiles."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migrate_schema()
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        pls_id = (
            f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
            "Microsoft.Network/privateLinkServices/pls-a513a93d0619a4797851e4b700c3c2ce"
        )
        for _ in range(3):
            _upsert_resource(
                session,
                SUB,
                resource_id=pls_id,
                resource_name="pls-a513a93d0619a4797851e4b700c3c2ce",
                resource_type="network/privatelinkservice",
            )
        session.commit()
        assert session.query(ResourcePricingProfile).count() == 1
        profile = session.query(ResourcePricingProfile).first()
        assert profile.canonical_type == "network/privatelinkservice"
        assert profile.service_name == "Azure Private Link"
    finally:
        session.close()


def test_upsert_pricing_profile_dedupes_pending_session_rows():
    """With autoflush=False, repeated upserts must not insert duplicate pricing rows."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migrate_schema()
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        pe_id = (
            f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
            "Microsoft.Network/privateEndpoints/pe1"
        )
        for _ in range(2):
            _upsert_resource(
                session,
                SUB,
                resource_id=pe_id,
                resource_name="pe1",
                resource_type="network/privateendpoint",
            )
        session.commit()
        assert session.query(ResourcePricingProfile).count() == 1
        assert session.query(ResourcePricingProfile).first().service_name == "Azure Private Link"
    finally:
        session.close()

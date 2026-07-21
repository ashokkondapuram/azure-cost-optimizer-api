"""Tests for unified resource_sku_pricing cache."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.azure_retail_price_store import (
    SkuPriceRequest,
    lookup_cached_price,
    make_lookup_key,
    upsert_sku_price,
)
from app.models import Base, ResourceSkuPricing
from app.resource_retail_cost import estimate_resource_retail_monthly
from app.retail_price_sync import seed_catalog_disk_prices


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_make_lookup_key_disk():
    key = make_lookup_key("compute/disk", "East US", "Premium_LRS", capacity_gb=128)
    assert key == "compute/disk|eastus|premium_lrs|128"


def test_upsert_and_lookup_disk_price(db):
    upsert_sku_price(
        db,
        canonical_type="compute/disk",
        region="eastus",
        arm_sku_name="Premium_LRS",
        capacity_gb=128,
        monthly_price_usd=19.71,
        price_source="azure_retail_prices",
        sku_details={"tier": "premium", "retail_code": "P30"},
    )
    db.commit()

    cached = lookup_cached_price(
        db,
        SkuPriceRequest(
            canonical_type="compute/disk",
            region="eastus",
            arm_sku_name="Premium_LRS",
            capacity_gb=128,
        ),
    )
    assert cached is not None
    assert cached["monthly_price_usd"] == pytest.approx(19.71)
    assert cached["price_source"] == "azure_retail_prices"


def test_estimate_disk_retail_from_db_cache(db):
    upsert_sku_price(
        db,
        canonical_type="compute/disk",
        region="eastus",
        arm_sku_name="Premium_LRS",
        capacity_gb=128,
        monthly_price_usd=19.71,
        price_source="azure_retail_prices",
    )
    db.commit()

    result = estimate_resource_retail_monthly(
        {
            "type": "compute/disk",
            "location": "eastus",
            "sku": "Premium_LRS",
            "properties": {"diskSizeGB": 128},
            "billingCurrency": "CAD",
        },
        db,
    )
    assert result["retail_monthly"] == pytest.approx(19.71)
    assert result["retail_source"] == "azure_retail_prices"
    assert result["retail_pending"] is False


def test_seed_catalog_disk_prices_writes_rows(db):
    written = seed_catalog_disk_prices(db, regions=["eastus"])
    db.commit()
    assert written > 0
    row = (
        db.query(ResourceSkuPricing)
        .filter(ResourceSkuPricing.lookup_key == "compute/disk|eastus|premium_lrs|128")
        .first()
    )
    assert row is not None
    assert row.price_source == "catalog_fallback"
    assert row.monthly_price_usd > 0


@patch("app.azure_retail_pricing.get_managed_disk_monthly_price", return_value=18.5)
def test_estimate_disk_falls_back_to_api_when_db_empty(mock_price, db):
    result = estimate_resource_retail_monthly(
        {
            "type": "compute/disk",
            "location": "eastus",
            "sku": "Premium_LRS",
            "properties": {"diskSizeGB": 128},
        },
        db,
    )
    assert result["retail_monthly"] == pytest.approx(18.5)
    mock_price.assert_called_once()

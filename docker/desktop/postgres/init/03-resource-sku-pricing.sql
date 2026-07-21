-- Unified Azure retail / catalog SKU price cache (global rows, subscription_id NULL).

CREATE TABLE IF NOT EXISTS resource_sku_pricing (
    id                VARCHAR PRIMARY KEY,
    subscription_id   VARCHAR,
    canonical_type    VARCHAR NOT NULL,
    arm_sku_name      VARCHAR NOT NULL,
    sku_name          VARCHAR,
    region            VARCHAR NOT NULL,
    capacity_gb       INTEGER,
    os_type           VARCHAR,
    lookup_key        VARCHAR NOT NULL,
    unit_price        DOUBLE PRECISION,
    unit_of_measure   VARCHAR,
    monthly_price_usd DOUBLE PRECISION NOT NULL,
    currency          VARCHAR DEFAULT 'USD',
    price_source      VARCHAR NOT NULL,
    sku_details_json  TEXT DEFAULT '{}',
    fetched_at        TIMESTAMPTZ DEFAULT NOW(),
    expires_at        TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rsp_lookup_key ON resource_sku_pricing (lookup_key);
CREATE INDEX IF NOT EXISTS ix_rsp_canonical_region ON resource_sku_pricing (canonical_type, region);
CREATE INDEX IF NOT EXISTS ix_rsp_expires ON resource_sku_pricing (expires_at);
CREATE INDEX IF NOT EXISTS ix_rsp_fetched ON resource_sku_pricing (fetched_at);

-- Individual assessment property values (EAV) for resource enrichment.
-- Applied automatically via app.database.migrate_schema() on startup.
-- Replaces opaque properties_json blobs for inventory/assessment fields.

CREATE TABLE IF NOT EXISTS resource_enrichment_property_values (
    id               VARCHAR PRIMARY KEY,
    resource_id      VARCHAR NOT NULL,
    arm_id           VARCHAR NOT NULL,
    subscription_id  VARCHAR NOT NULL,
    canonical_type   VARCHAR NOT NULL,
    property_key     VARCHAR NOT NULL,
    property_value   VARCHAR,
    value_type       VARCHAR,
    group_key        VARCHAR,
    label            VARCHAR,
    unit             VARCHAR DEFAULT '',
    updated_at       TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'utc'),
    CONSTRAINT uq_rep_sub_arm_type_key UNIQUE (subscription_id, arm_id, canonical_type, property_key)
);

CREATE INDEX IF NOT EXISTS ix_rep_resource ON resource_enrichment_property_values (resource_id);
CREATE INDEX IF NOT EXISTS ix_rep_sub_type ON resource_enrichment_property_values (subscription_id, canonical_type);

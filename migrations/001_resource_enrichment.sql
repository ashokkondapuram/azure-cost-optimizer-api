-- Unified resource enrichment table (Workstream 2)
-- Applied automatically via app.database.migrate_schema() on startup.
-- Run manually against Postgres when deploying outside the app process.

CREATE TABLE IF NOT EXISTS resource_enrichment (
    id                  VARCHAR PRIMARY KEY,
    resource_id         VARCHAR NOT NULL,
    arm_id              VARCHAR NOT NULL,
    canonical_type      VARCHAR NOT NULL,
    subscription_id     VARCHAR NOT NULL,
    properties_json     TEXT DEFAULT '{}',
    metrics_json        TEXT DEFAULT '{}',
    cost_json           TEXT DEFAULT '{}',
    recommendations_json TEXT DEFAULT '{}',
    enriched_at         TIMESTAMPTZ,
    metrics_at          TIMESTAMPTZ,
    cost_at             TIMESTAMPTZ,
    analysis_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at          TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'utc'),
    CONSTRAINT uq_re_sub_arm UNIQUE (subscription_id, arm_id)
);

CREATE INDEX IF NOT EXISTS ix_re_sub_canonical ON resource_enrichment (subscription_id, canonical_type);
CREATE INDEX IF NOT EXISTS ix_re_snapshot ON resource_enrichment (resource_id);
CREATE INDEX IF NOT EXISTS ix_re_arm ON resource_enrichment (arm_id);

-- resource_id references resource_snapshots.id (logical FK; not enforced for SQLite dev).

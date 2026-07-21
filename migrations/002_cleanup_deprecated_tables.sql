-- Drop deprecated tables after per-type enrichment migration.
-- Run after 001_resource_enrichment.sql and app migrate_schema() has copied unified rows.
-- Safe to re-run: IF EXISTS guards.

DROP TABLE IF EXISTS resource_normalized_snapshots;
DROP TABLE IF EXISTS resource_utilization_history;
DROP TABLE IF EXISTS resource_enrichment;

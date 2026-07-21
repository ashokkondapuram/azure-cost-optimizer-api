# Migrations — SQL schema changes

Manual SQL migrations applied to PostgreSQL outside of Alembic. Run in order when setting up or upgrading a database.

## Files

| File | Purpose |
|------|---------|
| `001_resource_enrichment.sql` | Resource enrichment tables |
| `002_cleanup_deprecated_tables.sql` | Remove legacy tables |
| `002_per_type_resource_enrichment.sql` | Per-type enrichment schema |
| `003_enrichment_property_values.sql` | Property value storage |

## Apply (local Postgres)

```bash
psql "$DATABASE_URL" -f migrations/001_resource_enrichment.sql
# … continue in numeric order
```

Docker Desktop applies base schema via `docker/desktop/postgres/init/` on first container start. Use these migrations for incremental changes on existing databases.

## Parent

[Repository root](../README.md)

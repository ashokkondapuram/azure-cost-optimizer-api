"""IT service entity — public exports for PostgreSQL flexible server."""

from __future__ import annotations

SERVICE_ID = "database-postgresql"
CANONICAL_TYPE = "database/postgresql"
ARM_TYPE = "Microsoft.DBforPostgreSQL/flexibleServers"
DISPLAY_NAME = "PostgreSQL flexible server"
API_SLUG = "postgresql"
COMPONENT = "PostgreSQL"

from it_services.database_postgresql.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.database_postgresql.engine.sub_engine import PostgresqlSubEngine as SubEngine


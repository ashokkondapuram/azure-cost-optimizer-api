"""IT service entity — public exports for SQL server."""

from __future__ import annotations

SERVICE_ID = "database-sql"
CANONICAL_TYPE = "database/sql"
ARM_TYPE = "Microsoft.Sql/servers"
DISPLAY_NAME = "SQL server"
API_SLUG = "sql"
COMPONENT = "SQL Database"

from it_services.database_sql.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.database_sql.engine.sub_engine import SqlSubEngine as SubEngine


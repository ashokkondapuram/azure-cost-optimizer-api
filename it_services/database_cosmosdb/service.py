"""IT service entity — public exports for Cosmos DB account."""

from __future__ import annotations

SERVICE_ID = "database-cosmosdb"
CANONICAL_TYPE = "database/cosmosdb"
ARM_TYPE = "Microsoft.DocumentDB/databaseAccounts"
DISPLAY_NAME = "Cosmos DB account"
API_SLUG = "cosmosdb"
COMPONENT = "Cosmos DB"

from it_services.database_cosmosdb.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.database_cosmosdb.engine.sub_engine import CosmosSubEngine as SubEngine


"""Resource profile — owned by database-sql IT service."""

from app.resources.types import TechnicalFetchSpec, field

CANONICAL_TYPE = "database/sql"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Sql/servers",
    display_name="SQL server",
    sync_property_paths=("version", "state", "minimalTlsVersion", "publicNetworkAccess"),
    fields=(
        field("version", "props:version", "SQL version", "configuration"),
        field("public_network_access", "props:publicNetworkAccess", "Public network access", "governance"),
    ),
)

MONITOR_PROFILE = None

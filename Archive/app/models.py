"""
Azure Cost Optimizer — SQLAlchemy Models

Design principles for performance:
  - All hot-path query columns are indexed.
  - Composite indexes cover the most common (subscription_id, synced_at) filter pattern.
  - JSONB-style data stored as Text (works on SQLite dev / Postgres prod).
  - resource_snapshots partitioned logically by resource_type via a filtered index.
  - Soft-delete with is_active flag keeps history without large DELETEs.
  - cost_snapshots has a unique constraint so upserts are idempotent.
"""

from sqlalchemy import (
    Column, String, DateTime, Text, Float, Boolean,
    Integer, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Subscriptions cache
# ---------------------------------------------------------------------------

class SubscriptionCache(Base):
    """
    Caches the list of Azure subscriptions so the sidebar loads instantly.
    Refreshed by /api/resources/sync.
    """
    __tablename__ = "subscription_cache"

    subscription_id = Column(String, primary_key=True)
    display_name    = Column(String)
    state           = Column(String)   # Enabled | Disabled | Warned
    tenant_id       = Column(String)
    raw_json        = Column(Text)     # full ARM object
    synced_at       = Column(DateTime(timezone=True), default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# Resource snapshots  (one row per resource per sync)
# ---------------------------------------------------------------------------

class ResourceSnapshot(Base):
    """
    Universal resource table. Every Azure resource type (VM, Disk, AKS,
    Storage, Public IP, SQL, Key Vault, App Service, LB, CosmosDB,
    PostgreSQL, NSG, ACR, App Gateway …) lands here.

    resource_type values (canonical):
        compute/vm | compute/disk | containers/aks | containers/acr
        storage/account | network/publicip | network/loadbalancer
        network/appgateway | network/nsg | database/sql
        database/cosmosdb | database/postgresql | appservice/webapp
        security/keyvault

    Performance indexes:
        ix_rs_sub_type_active   — primary list queries (subscription + type)
        ix_rs_sub_synced        — latest-sync queries
        ix_rs_resource_id       — point lookups by ARM resource ID
    """
    __tablename__ = "resource_snapshots"
    __table_args__ = (
        Index("ix_rs_sub_type_active",  "subscription_id", "resource_type", "is_active"),
        Index("ix_rs_sub_synced",       "subscription_id", "synced_at"),
        Index("ix_rs_resource_id",      "resource_id"),
        Index("ix_rs_rg",               "subscription_id", "resource_group"),
    )

    id              = Column(String,  primary_key=True)   # uuid
    subscription_id = Column(String,  nullable=False)
    resource_id     = Column(String,  nullable=False)     # ARM /subscriptions/.../resourceId
    resource_name   = Column(String,  nullable=False)
    resource_type   = Column(String,  nullable=False)     # canonical category/subtype
    resource_group  = Column(String)
    location        = Column(String)
    sku             = Column(String)                      # VM size, storage tier, etc.
    state           = Column(String)                      # running/stopped/deallocated/etc.
    tags_json       = Column(Text,    default="{}")       # Azure tags as JSON
    properties_json = Column(Text,    default="{}")       # full ARM properties subset
    monthly_cost_usd = Column(Float,  default=0.0)        # last known cost
    is_active       = Column(Boolean, default=True)       # False = deleted from Azure
    synced_at       = Column(DateTime(timezone=True), default=_now)
    created_at      = Column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# Cost snapshots  (MTD / daily granularity per subscription)
# ---------------------------------------------------------------------------

class CostSnapshot(Base):
    """
    Stores daily Azure cost roll-ups. Unique on (subscription_id, date, granularity)
    so repeated syncs are idempotent UPSERTs.

    Indexes:
        ix_cs_sub_date   — time-series queries
        ix_cs_rg_date    — resource-group breakdown queries
    """
    __tablename__ = "cost_snapshots"
    __table_args__ = (
        UniqueConstraint("subscription_id", "cost_date", "granularity", "resource_group",
                         name="uq_cost_snapshot"),
        Index("ix_cs_sub_date",  "subscription_id", "cost_date"),
        Index("ix_cs_rg_date",   "subscription_id", "resource_group", "cost_date"),
    )

    id              = Column(String,  primary_key=True)
    subscription_id = Column(String,  nullable=False)
    cost_date       = Column(String,  nullable=False)   # YYYY-MM-DD
    granularity     = Column(String,  default="Daily")  # Daily | Monthly
    resource_group  = Column(String,  nullable=True)
    cost_usd        = Column(Float,   nullable=False)
    currency        = Column(String,  default="USD")
    synced_at       = Column(DateTime(timezone=True), default=_now)


class CostByServiceSnapshot(Base):
    """
    MTD cost aggregated by Azure service name (e.g. 'Virtual Machines', 'Storage').
    Refreshed on every sync. One row per (subscription_id, service_name, month).
    """
    __tablename__ = "cost_by_service"
    __table_args__ = (
        UniqueConstraint("subscription_id", "service_name", "month",
                         name="uq_cost_by_service"),
        Index("ix_cbs_sub_month", "subscription_id", "month"),
    )

    id              = Column(String, primary_key=True)
    subscription_id = Column(String, nullable=False)
    service_name    = Column(String, nullable=False)
    month           = Column(String, nullable=False)   # YYYY-MM
    cost_usd        = Column(Float,  nullable=False)
    synced_at       = Column(DateTime(timezone=True), default=_now)


class BudgetSnapshot(Base):
    """
    Azure budget definitions + current spend cached locally.
    """
    __tablename__ = "budget_snapshots"
    __table_args__ = (
        Index("ix_bs_sub", "subscription_id"),
    )

    id              = Column(String, primary_key=True)
    subscription_id = Column(String, nullable=False)
    budget_name     = Column(String)
    amount          = Column(Float)
    time_grain      = Column(String)   # Monthly | Quarterly | Annually
    current_spend   = Column(Float,  default=0.0)
    forecast_spend  = Column(Float,  default=0.0)
    currency        = Column(String, default="USD")
    synced_at       = Column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# Existing tables (unchanged — kept for Alembic continuity)
# ---------------------------------------------------------------------------

class CostRecord(Base):
    __tablename__ = "cost_records"
    id              = Column(String, primary_key=True)
    subscription_id = Column(String, nullable=False, index=True)
    resource_group  = Column(String, nullable=True)
    timeframe       = Column(String)
    granularity     = Column(String)
    raw_response    = Column(Text)
    created_at      = Column(DateTime(timezone=True), default=_now)


class K8sUtilization(Base):
    __tablename__ = "k8s_utilization"
    id           = Column(String, primary_key=True)
    cluster_name = Column(String, index=True)
    node_name    = Column(String)
    pod_name     = Column(String, nullable=True)
    namespace    = Column(String, nullable=True)
    cpu_usage    = Column(String)
    memory_usage = Column(String)
    recorded_at  = Column(DateTime(timezone=True), default=_now)


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"
    __table_args__ = (
        Index("ix_or_sub_analyzed", "subscription_id", "analyzed_at"),
    )
    id                = Column(String,  primary_key=True)
    subscription_id   = Column(String,  index=True)
    profile           = Column(String,  default="default")
    total_findings    = Column(Integer, default=0)
    critical_count    = Column(Integer, default=0)
    high_count        = Column(Integer, default=0)
    medium_count      = Column(Integer, default=0)
    low_count         = Column(Integer, default=0)
    total_savings_usd = Column(Float,   default=0.0)
    findings_json     = Column(Text)
    analyzed_at       = Column(DateTime(timezone=True), default=_now)


class EngineConfig(Base):
    __tablename__ = "engine_configs"
    id             = Column(String,  primary_key=True)
    profile        = Column(String,  default="default", index=True)
    rule_id        = Column(String,  nullable=False, index=True)
    enabled        = Column(Boolean, default=True)
    overrides_json = Column(Text,    default="{}")
    description    = Column(String,  nullable=True)
    updated_at     = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class OptimizationFinding(Base):
    __tablename__ = "optimization_findings"
    __table_args__ = (
        Index("ix_of_sub_status",   "subscription_id", "status"),
        Index("ix_of_sub_severity", "subscription_id", "severity"),
        Index("ix_of_run_rule",     "run_id", "rule_id"),
    )
    id                    = Column(String,  primary_key=True)
    run_id                = Column(String,  index=True)
    rule_id               = Column(String,  index=True)
    rule_name             = Column(String)
    category              = Column(String,  index=True)
    severity              = Column(String,  index=True)
    resource_id           = Column(String,  index=True)
    resource_name         = Column(String)
    resource_type         = Column(String)
    subscription_id       = Column(String,  index=True)
    resource_group        = Column(String)
    location              = Column(String)
    detail                = Column(Text)
    recommendation        = Column(Text)
    estimated_savings_usd = Column(Float,   default=0.0)
    waste_score           = Column(Integer, default=0)
    status                = Column(String,  default="open")
    resolved_at           = Column(DateTime(timezone=True), nullable=True)
    detected_at           = Column(DateTime(timezone=True), default=_now)

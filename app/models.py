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
from sqlalchemy.orm import deferred
from datetime import datetime, timezone

from app.db_types import JSONText

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
        UniqueConstraint("subscription_id", "resource_id", name="uq_rs_sub_resource"),
        Index("ix_rs_sub_type_active",  "subscription_id", "resource_type", "is_active"),
        Index("ix_rs_sub_synced",       "subscription_id", "synced_at"),
        Index("ix_rs_resource_id",      "resource_id"),
        Index("ix_rs_rg",               "subscription_id", "resource_group"),
        Index("ix_rs_sub_type",         "subscription_id", "resource_type"),
        Index("ix_rs_sub_active",       "subscription_id", "is_active"),
        Index("ix_rs_type",             "resource_type"),
        Index("ix_rs_sub_export",       "subscription_id", "is_cost_export_only"),
    )

    id              = Column(String,  primary_key=True)   # uuid
    subscription_id = Column(String,  nullable=False)
    resource_id     = Column(String,  nullable=False)     # ARM /subscriptions/.../resourceId
    resource_name   = Column(String,  nullable=False)
    resource_type   = Column(String,  nullable=False)     # canonical category/subtype
    resource_group  = Column(String)
    location        = Column(String)
    sku             = Column(String)                      # VM size, storage tier, etc.
    sku_json        = deferred(Column(JSONText, default="{}"))
    state           = Column(String)                      # running/stopped/deallocated/etc.
    tags_json       = deferred(Column(JSONText, default="{}"))
    properties_json = deferred(Column(JSONText, default="{}"))
    monthly_cost_billing = Column(Float, default=0.0)     # MTD BilledCost (billing currency)
    monthly_cost_usd     = Column(Float, default=0.0)     # MTD x_BilledCostInUsd
    billing_currency     = Column(String, default="CAD")  # BillingCurrency from export
    azure_service_name   = Column(String, nullable=True)    # ServiceName from FOCUS export
    is_active       = Column(Boolean, default=True)       # False = deleted from Azure
    is_cost_export_only = Column(Boolean, default=False, index=True)
    synced_at       = Column(DateTime(timezone=True), default=_now)
    created_at      = Column(DateTime(timezone=True), default=_now)
    # Optimization analysis summary (updated by POST /optimize/analyze with data_source=db)
    analysis_findings_count = Column(Integer, default=0)
    analysis_savings_usd    = Column(Float,   default=0.0)
    analysis_top_severity   = Column(String,  nullable=True)
    analysis_updated_at     = Column(DateTime(timezone=True), nullable=True)
    analysis_run_id         = Column(String,  nullable=True)
    analysis_data_source    = Column(String,  nullable=True)
    analysis_summary_json   = deferred(Column(Text,    default="[]"))


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
    cost_billing    = Column(Float,   nullable=True)    # PreTaxCost / BilledCost (billing currency)
    currency        = Column(String,  default="CAD")
    synced_at       = Column(DateTime(timezone=True), default=_now)


class CostDailyByServiceSnapshot(Base):
    """
    Daily cost per Azure service name. One row per (subscription_id, cost_date, service_name).
    Populated from the cost export on fetch/sync.
    """
    __tablename__ = "cost_daily_by_service"
    __table_args__ = (
        UniqueConstraint("subscription_id", "cost_date", "service_name",
                         name="uq_cost_daily_by_service"),
        Index("ix_cdbs_sub_date", "subscription_id", "cost_date"),
        Index("ix_cdbs_sub_svc", "subscription_id", "service_name", "cost_date"),
    )

    id               = Column(String, primary_key=True)
    subscription_id  = Column(String, nullable=False)
    cost_date        = Column(String, nullable=False)   # YYYY-MM-DD
    service_name     = Column(String, nullable=False)
    cost_usd         = Column(Float,  nullable=False)
    cost_billing     = Column(Float,  nullable=True)
    billing_currency = Column(String, default="CAD")
    synced_at        = Column(DateTime(timezone=True), default=_now)


class CostByResourceSnapshot(Base):
    """
    MTD cost per ARM resource from Cost Management.
    One row per (subscription_id, resource_id, month).
    Populated by the cost explorer worker and optimization flows.
    """
    __tablename__ = "cost_by_resource"
    __table_args__ = (
        UniqueConstraint("subscription_id", "resource_id", "month",
                         name="uq_cost_by_resource"),
        Index("ix_cbr_sub_month", "subscription_id", "month"),
        Index("ix_cbr_sub_service", "subscription_id", "service_name", "month"),
        Index("ix_cbr_resource_id", "resource_id"),
    )

    id               = Column(String, primary_key=True)
    subscription_id  = Column(String, nullable=False)
    resource_id      = Column(String, nullable=False)
    service_name     = Column(String, nullable=False)
    resource_group   = Column(String, nullable=True)
    resource_type    = Column(String, nullable=True)
    month            = Column(String, nullable=False)   # YYYY-MM
    cost_usd         = Column(Float, nullable=False)
    cost_billing     = Column(Float, nullable=True)
    billing_currency = Column(String, default="CAD")
    synced_at        = Column(DateTime(timezone=True), default=_now)
    azure_exists     = Column(Boolean, nullable=True)
    azure_checked_at = Column(DateTime(timezone=True), nullable=True)


class CostByResourceTypeSnapshot(Base):
    """
    MTD cost aggregated by ARM resource type (subscription-wide).
    Used by the cost explorer worker for Dashboard and Cost explorer tabs.
    """
    __tablename__ = "cost_by_resource_type"
    __table_args__ = (
        UniqueConstraint("subscription_id", "arm_resource_type", "month",
                         name="uq_cost_by_resource_type"),
        Index("ix_cbrt_sub_month", "subscription_id", "month"),
    )

    id                      = Column(String, primary_key=True)
    subscription_id         = Column(String, nullable=False)
    arm_resource_type       = Column(String, nullable=False)
    canonical_resource_type = Column(String, nullable=True)
    month                   = Column(String, nullable=False)
    cost_usd                = Column(Float, nullable=False)
    cost_billing            = Column(Float, nullable=True)
    billing_currency        = Column(String, default="CAD")
    synced_at               = Column(DateTime(timezone=True), default=_now)


class CostSyncRun(Base):
    """
    One row per Fetch costs run. Stores MTD service totals and deltas vs the prior fetch.
    """
    __tablename__ = "cost_sync_runs"
    __table_args__ = (
        Index("ix_csr_sub_month", "subscription_id", "month"),
        Index("ix_csr_sub_synced", "subscription_id", "synced_at"),
    )

    id                 = Column(String, primary_key=True)
    subscription_id    = Column(String, nullable=False)
    month              = Column(String, nullable=False)
    mtd_start          = Column(String, nullable=False)
    mtd_end            = Column(String, nullable=False)
    total_billing      = Column(Float, nullable=False, default=0.0)
    total_usd          = Column(Float, nullable=False, default=0.0)
    billing_currency   = Column(String, default="USD")
    services_json      = Column(Text, default="[]")
    changes_json       = Column(Text, default="[]")
    previous_synced_at = Column(DateTime(timezone=True), nullable=True)
    synced_at          = Column(DateTime(timezone=True), default=_now)


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
    cost_usd        = Column(Float,  nullable=False)   # Azure CostUSD (USD)
    cost_billing    = Column(Float,  nullable=True)    # Azure PreTaxCost (billing currency)
    billing_currency = Column(String, default="CAD")   # Azure Currency column (e.g. CAD)
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


class ComponentSyncState(Base):
    """Last successful per-component inventory sync (rotating worker)."""
    __tablename__ = "component_sync_state"

    component    = Column(String, primary_key=True)
    synced_at    = Column(DateTime(timezone=True), nullable=False)
    last_status  = Column(String, nullable=True)
    updated_at   = Column(DateTime(timezone=True), default=_now, onupdate=_now)


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


class K8sSnapshot(Base):
    """Full cluster snapshot pushed by the in-cluster utilization agent."""
    __tablename__ = "k8s_snapshots"
    __table_args__ = (
        Index("ix_k8s_snap_cluster_time", "cluster_name", "recorded_at"),
    )
    id           = Column(String, primary_key=True)
    cluster_name = Column(String, index=True, nullable=False)
    node_count   = Column(Integer, default=0)
    pod_count    = Column(Integer, default=0)
    payload_json = Column(Text, default="{}")
    recorded_at  = Column(DateTime(timezone=True), default=_now)


class ResourceUtilizationHistory(Base):
    """
    Weekly utilization snapshots captured after each analysis run.
    One row per (subscription, resource, metric, snapshot_date).
    Retained ~6 months for trend analysis and demand forecasting.
    """
    __tablename__ = "resource_utilization_history"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "resource_id", "metric_name", "snapshot_date",
            name="uq_util_hist",
        ),
        Index("ix_ruh_sub_resource", "subscription_id", "resource_id"),
        Index("ix_ruh_resource_metric", "resource_id", "metric_name", "snapshot_date"),
    )

    id              = Column(String, primary_key=True)
    subscription_id = Column(String, nullable=False)
    resource_id     = Column(String, nullable=False)
    metric_name     = Column(String, nullable=False)
    snapshot_date   = Column(String, nullable=False)   # YYYY-MM-DD
    recorded_at     = Column(DateTime(timezone=True), default=_now)
    value_avg       = Column(Float, nullable=True)
    value_max       = Column(Float, nullable=True)
    value_min       = Column(Float, nullable=True)
    period_days     = Column(Integer, default=7)


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
    engine_version    = Column(String,  default="standard")
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


class SystemSetting(Base):
    """Runtime configuration stored in the database (secrets encrypted at rest)."""
    __tablename__ = "system_settings"

    id          = Column(String, primary_key=True)
    category    = Column(String, unique=True, nullable=False, index=True)
    config_json = Column(Text, default="{}")
    updated_at  = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class AppUser(Base):
    """Application login accounts (separate from Azure service identity)."""
    __tablename__ = "app_users"
    __table_args__ = (
        Index("ix_app_users_username", "username", unique=True),
    )

    id            = Column(String, primary_key=True)
    username      = Column(String, nullable=False, unique=True)
    display_name  = Column(String)
    password_hash = Column(String, nullable=False)
    role          = Column(String, nullable=False, default="viewer")  # admin | viewer
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), default=_now)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class FindingActivity(Base):
    """Audit trail for finding status changes and notes."""
    __tablename__ = "finding_activity"
    __table_args__ = (
        Index("ix_fa_finding_created", "finding_id", "created_at"),
        Index("ix_fa_sub_created", "subscription_id", "created_at"),
    )

    id              = Column(String, primary_key=True)
    finding_id      = Column(String, nullable=False, index=True)
    subscription_id = Column(String, nullable=False)
    action          = Column(String, nullable=False, default="status_change")
    from_status     = Column(String, nullable=True)
    to_status       = Column(String, nullable=True)
    user_id         = Column(String, nullable=True)
    user_name       = Column(String, nullable=True)
    note            = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=_now)


class AnalysisJob(Base):
    """Background batch optimization job — processes one component at a time."""
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_aj_sub_status", "subscription_id", "status"),
        Index("ix_aj_created", "created_at"),
    )

    id                = Column(String, primary_key=True)
    subscription_id   = Column(String, nullable=False, index=True)
    profile           = Column(String, default="default")
    engine_version    = Column(String, default="extended")
    rule_overrides_json = Column(Text, default="{}")
    status            = Column(String, default="queued")  # queued|running|completed|failed
    progress_pct      = Column(Integer, default=0)
    current_component = Column(String, nullable=True)
    total_batches     = Column(Integer, default=0)
    completed_batches = Column(Integer, default=0)
    components_json   = Column(Text, default="[]")
    run_id            = Column(String, nullable=True)
    error_message     = Column(Text, nullable=True)
    created_at        = Column(DateTime(timezone=True), default=_now)
    started_at        = Column(DateTime(timezone=True), nullable=True)
    completed_at      = Column(DateTime(timezone=True), nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_key = Column(String(128), nullable=False, index=True)
    attempted_at = Column(DateTime(timezone=True), nullable=False)


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
    annualized_savings_usd = Column(Float,  default=0.0)
    waste_score           = Column(Integer, default=0)
    confidence_score      = Column(Integer, default=0)
    action_priority       = Column(String,  nullable=True)
    impact                = Column(Text,    nullable=True)
    evidence_json         = Column(JSONText, default="{}")
    status                = Column(String,  default="open")
    resolved_at           = Column(DateTime(timezone=True), nullable=True)
    chain_id              = Column(String(64), nullable=True)
    chain_step            = Column(Integer, nullable=True)
    chain_total           = Column(Integer, nullable=True)
    advisor_recommendation_id = Column(String, nullable=True, index=True)
    linked_action_id        = Column(String, nullable=True, index=True)
    detected_at           = Column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# Resource pricing profiles (SKU + pricing model per synced resource)
# ---------------------------------------------------------------------------

class ResourceDependency(Base):
    """Discovered dependency edges between Azure resources (3-C)."""
    __tablename__ = "resource_dependencies"
    __table_args__ = (
        Index("ix_rd_sub_source", "subscription_id", "source_resource_id"),
        Index("ix_rd_sub_target", "subscription_id", "target_resource_id"),
    )

    id                 = Column(String, primary_key=True)
    subscription_id    = Column(String, nullable=False, index=True)
    source_resource_id = Column(String, nullable=False)
    target_resource_id = Column(String, nullable=False)
    dependency_type    = Column(String, nullable=False)
    criticality        = Column(String, nullable=True, default="medium")
    discovered_at      = Column(DateTime(timezone=True), default=_now)


class RecommendationExecution(Base):
    """Closed-loop tracking when a recommendation is applied (3-D)."""
    __tablename__ = "recommendation_executions"
    __table_args__ = (
        Index("ix_re_finding", "finding_id"),
        Index("ix_re_executed", "executed_at"),
    )

    id                = Column(String, primary_key=True)
    finding_id        = Column(String, nullable=False, index=True)
    executed_by       = Column(String, nullable=False)
    executed_at       = Column(DateTime(timezone=True), default=_now)
    before_state      = Column(Text, default="{}")
    after_state       = Column(Text, default="{}")
    action_type       = Column(String, nullable=False)
    validation_status = Column(String, default="pending")
    validated_at      = Column(DateTime(timezone=True), nullable=True)


class ResourcePricingProfile(Base):
    """
    Resolved SKU and pricing model for each inventoried resource.
    Populated during inventory sync from the Azure service cost catalog.
    """
    __tablename__ = "resource_pricing_profiles"
    __table_args__ = (
        UniqueConstraint("subscription_id", "resource_id", name="uq_rpp_sub_resource"),
        Index("ix_rpp_sub_type", "subscription_id", "canonical_type"),
        Index("ix_rpp_sub_synced", "subscription_id", "synced_at"),
    )

    id              = Column(String, primary_key=True)
    subscription_id = Column(String, nullable=False)
    resource_id     = Column(String, nullable=False)
    resource_name   = Column(String, nullable=False)
    canonical_type  = Column(String, nullable=False)
    sku             = Column(String)
    sku_name        = Column(String)
    sku_tier        = Column(String)
    pricing_model   = Column(String, nullable=False)
    cost_type       = Column(String, nullable=False)
    service_name    = Column(String)
    free_tier_json  = Column(Text, default="{}")
    profile_json    = Column(Text, default="{}")
    synced_at       = Column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# Azure Advisor recommendation snapshots
# ---------------------------------------------------------------------------

class AdvisorRecommendation(Base):
    """Persisted snapshot of a Microsoft.Advisor recommendation."""
    __tablename__ = "advisor_recommendations"
    __table_args__ = (
        UniqueConstraint("subscription_id", "recommendation_id", name="uq_advisor_sub_rec"),
        Index("ix_advisor_sub_category", "subscription_id", "category"),
        Index("ix_advisor_resource_id", "resource_id"),
        Index("ix_advisor_generated", "generated_at"),
    )

    id                        = Column(String, primary_key=True)
    recommendation_id         = Column(String, nullable=False)
    resource_id               = Column(String, nullable=False, index=True)
    subscription_id           = Column(String, nullable=False, index=True)
    category                  = Column(String, nullable=False)
    impact                    = Column(String, nullable=False)
    summary                   = Column(String, nullable=False)
    description               = Column(Text, nullable=True)
    potential_savings_monthly = Column(Float, nullable=True)
    potential_savings_yearly  = Column(Float, nullable=True)
    status                    = Column(String, nullable=False, default="Active")
    generated_at              = Column(DateTime(timezone=True), nullable=False)
    synced_at                 = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    raw_json                  = Column(JSONText, default="{}")
    app_override              = Column(Boolean, default=False)


class OptimizationAction(Base):
    """Synthesized optimization action per resource (Advisor + engine findings)."""
    __tablename__ = "optimization_actions"
    __table_args__ = (
        UniqueConstraint("subscription_id", "resource_id", name="uq_action_sub_resource"),
        Index("ix_action_sub_status", "subscription_id", "workflow_status"),
        Index("ix_action_resource", "resource_id"),
        Index("ix_action_confidence", "confidence"),
    )

    id                        = Column(String, primary_key=True)
    resource_id               = Column(String, nullable=False, index=True)
    subscription_id           = Column(String, nullable=False, index=True)
    resource_type             = Column(String, nullable=False)
    resource_name             = Column(String, nullable=True)
    action_type               = Column(String, nullable=False)
    action_reason             = Column(String, nullable=True)
    confidence                = Column(String, nullable=False, default="Medium")
    performance_risk          = Column(String, nullable=False, default="Low")
    estimated_monthly_savings = Column(Float, nullable=True)
    owner                     = Column(String, nullable=True)
    workflow_status           = Column(String, nullable=False, default="proposed")
    advisor_finding           = Column(JSONText, default="{}")
    cost_evidence             = Column(JSONText, default="{}")
    utilization_evidence      = Column(JSONText, default="{}")
    decision_rules_applied    = Column(JSONText, default="[]")
    workflow_history_json     = Column(JSONText, default="[]")
    recommendation_tier       = Column(String, nullable=True)
    overall_score             = Column(Float, nullable=True)
    created_at                = Column(DateTime(timezone=True), default=_now)
    updated_at                = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class WorkloadProfile(Base):
    """Cached workload characterization per resource."""
    __tablename__ = "workload_profiles"
    __table_args__ = (
        UniqueConstraint("subscription_id", "resource_id", name="uq_workload_sub_resource"),
        Index("ix_wp_sub_type", "subscription_id", "workload_type"),
    )

    id                              = Column(String, primary_key=True)
    resource_id                     = Column(String, nullable=False, index=True)
    subscription_id                 = Column(String, nullable=False, index=True)
    workload_type                   = Column(String, nullable=True)
    burstiness_score                = Column(Float, nullable=True)
    peak_hour_factor                = Column(Float, nullable=True)
    utilization_trend               = Column(String, nullable=True)
    utilization_variance_7d         = Column(Float, nullable=True)
    utilization_variance_30d        = Column(Float, nullable=True)
    utilization_coefficient_variance = Column(Float, nullable=True)
    detected_seasonality            = Column(Boolean, default=False)
    seasonal_peak_percentage        = Column(Float, nullable=True)
    classifier_class                = Column(String, nullable=True)
    synced_at                       = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class OptimizationScoring(Base):
    """Multi-dimensional optimization scorecard per resource per day."""
    __tablename__ = "optimization_scoring"
    __table_args__ = (
        UniqueConstraint("subscription_id", "resource_id", "evaluation_date", name="uq_score_sub_resource_date"),
        Index("ix_os_sub_tier", "subscription_id", "recommendation_tier"),
        Index("ix_os_sub_overall", "subscription_id", "overall_recommendation_score"),
    )

    id                                = Column(String, primary_key=True)
    resource_id                       = Column(String, nullable=False, index=True)
    subscription_id                   = Column(String, nullable=False, index=True)
    resource_name                     = Column(String, nullable=True)
    resource_type                     = Column(String, nullable=True)
    evaluation_date                   = Column(String, nullable=False)
    cost_savings_monthly              = Column(Float, nullable=True)
    cost_savings_confidence           = Column(Float, nullable=True)
    cost_payback_months               = Column(Integer, nullable=True)
    performance_risk_score            = Column(Float, nullable=True)
    dependency_blast_radius           = Column(Integer, nullable=True)
    dependency_criticality_max        = Column(String, nullable=True)
    sla_constraint_risk               = Column(Float, nullable=True)
    implementation_effort             = Column(String, nullable=True)
    automation_available              = Column(Boolean, default=False)
    workload_stability_score          = Column(Float, nullable=True)
    seasonal_impact_on_recommendation = Column(Float, nullable=True)
    business_priority_score           = Column(Float, nullable=True)
    business_criticality              = Column(String, nullable=True)
    cost_dimension_score              = Column(Float, nullable=True)
    safety_dimension_score            = Column(Float, nullable=True)
    effort_dimension_score            = Column(Float, nullable=True)
    workload_dimension_score          = Column(Float, nullable=True)
    business_dimension_score          = Column(Float, nullable=True)
    overall_recommendation_score      = Column(Float, nullable=True)
    recommendation_tier               = Column(String, nullable=True)
    primary_action                    = Column(String, nullable=True)
    action_confidence                 = Column(String, nullable=True)
    scoring_evidence_json             = Column(JSONText, default="{}")
    synced_at                         = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class OptimizationRolloutStage(Base):
    """Staged rollout batch with observation window for advanced engine actions."""
    __tablename__ = "optimization_rollout_stages"
    __table_args__ = (
        Index("ix_ors_sub_status", "subscription_id", "status"),
        Index("ix_ors_sub_tier", "subscription_id", "stage_tier"),
    )

    id                         = Column(String, primary_key=True)
    subscription_id            = Column(String, nullable=False, index=True)
    stage_number               = Column(Integer, nullable=False, default=1)
    stage_tier                 = Column(String, nullable=False)
    action_ids_json            = Column(JSONText, default="[]")
    resources_in_stage         = Column(Integer, nullable=False, default=0)
    resources_approved         = Column(Integer, nullable=False, default=0)
    resources_executed         = Column(Integer, nullable=False, default=0)
    resources_rolled_back      = Column(Integer, nullable=False, default=0)
    observation_window_days    = Column(Integer, nullable=False, default=7)
    observation_start_date     = Column(String, nullable=True)
    observation_metrics_json   = Column(JSONText, default="{}")
    post_change_metrics_json   = Column(JSONText, default="{}")
    rollback_triggered         = Column(Boolean, default=False)
    rollback_reason            = Column(Text, nullable=True)
    status                     = Column(String, nullable=False, default="proposed")
    created_at                 = Column(DateTime(timezone=True), default=_now)
    completed_at               = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Azure ARM token cache (PostgreSQL — shared across workers / restarts)
# ---------------------------------------------------------------------------

class AzureTokenCache(Base):
    """
    Cached Azure AD access tokens keyed by credential identity + scope.
    Tokens are encrypted at rest; rows are removed when expired or on credential reload.
    """
    __tablename__ = "azure_token_cache"
    __table_args__ = (
        Index("ix_atc_expires", "expires_at"),
    )

    cache_key    = Column(String, primary_key=True)
    scope        = Column(String, nullable=False)
    access_token = Column(Text, nullable=False)
    expires_at   = Column(DateTime(timezone=True), nullable=False)
    updated_at   = Column(DateTime(timezone=True), default=_now, onupdate=_now)

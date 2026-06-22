from sqlalchemy import Column, String, DateTime, Text, Float, Boolean, Integer
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class CostRecord(Base):
    __tablename__ = "cost_records"
    id              = Column(String, primary_key=True)
    subscription_id = Column(String, nullable=False, index=True)
    resource_group  = Column(String, nullable=True)
    timeframe       = Column(String)
    granularity     = Column(String)
    raw_response    = Column(Text)
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class K8sUtilization(Base):
    __tablename__ = "k8s_utilization"
    id           = Column(String, primary_key=True)
    cluster_name = Column(String, index=True)
    node_name    = Column(String)
    pod_name     = Column(String, nullable=True)
    namespace    = Column(String, nullable=True)
    cpu_usage    = Column(String)
    memory_usage = Column(String)
    recorded_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OptimizationRun(Base):
    """Persists each engine analysis run for history and trending."""
    __tablename__ = "optimization_runs"
    id                    = Column(String, primary_key=True)
    subscription_id       = Column(String, index=True)
    profile               = Column(String, default="default")
    total_findings        = Column(Integer, default=0)
    critical_count        = Column(Integer, default=0)
    high_count            = Column(Integer, default=0)
    medium_count          = Column(Integer, default=0)
    low_count             = Column(Integer, default=0)
    total_savings_usd     = Column(Float,   default=0.0)
    findings_json         = Column(Text)   # full JSON blob
    analyzed_at           = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EngineConfig(Base):
    """Per-profile, per-rule configuration overrides."""
    __tablename__ = "engine_configs"
    id             = Column(String, primary_key=True)
    profile        = Column(String, default="default", index=True)
    rule_id        = Column(String, nullable=False, index=True)
    enabled        = Column(Boolean, default=True)
    overrides_json = Column(Text, default="{}")  # JSON of threshold overrides
    description    = Column(String, nullable=True)
    updated_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))


class OptimizationFinding(Base):
    """Individual finding persisted for tracking remediation status."""
    __tablename__ = "optimization_findings"
    id                   = Column(String, primary_key=True)
    run_id               = Column(String, index=True)
    rule_id              = Column(String, index=True)
    rule_name            = Column(String)
    category             = Column(String, index=True)
    severity             = Column(String, index=True)
    resource_id          = Column(String, index=True)
    resource_name        = Column(String)
    resource_type        = Column(String)
    subscription_id      = Column(String, index=True)
    resource_group       = Column(String)
    location             = Column(String)
    detail               = Column(Text)
    recommendation       = Column(Text)
    estimated_savings_usd = Column(Float, default=0.0)
    waste_score          = Column(Integer, default=0)
    status               = Column(String, default="open")  # open | acknowledged | resolved | ignored
    resolved_at          = Column(DateTime(timezone=True), nullable=True)
    detected_at          = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

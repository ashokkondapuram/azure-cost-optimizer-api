from sqlalchemy import Column, String, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class CostRecord(Base):
    __tablename__ = "cost_records"
    id                = Column(String, primary_key=True)
    subscription_id   = Column(String, nullable=False, index=True)
    resource_group    = Column(String, nullable=True)
    timeframe         = Column(String)
    granularity       = Column(String)
    raw_response      = Column(Text)
    created_at        = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class K8sUtilization(Base):
    __tablename__ = "k8s_utilization"
    id            = Column(String, primary_key=True)
    cluster_name  = Column(String, index=True)
    node_name     = Column(String)
    pod_name      = Column(String, nullable=True)
    namespace     = Column(String, nullable=True)
    cpu_usage     = Column(String)
    memory_usage  = Column(String)
    recorded_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

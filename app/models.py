from sqlalchemy import Column, String, Float, DateTime, func
from app.database import Base


class CostRecord(Base):
    __tablename__ = "cost_records"

    id = Column(String, primary_key=True)  # UUID
    subscription_id = Column(String, nullable=False)
    resource_group = Column(String, nullable=True)
    timeframe = Column(String, nullable=False)
    granularity = Column(String, nullable=False)
    pretax_cost = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    billing_period = Column(String, nullable=True)
    raw_response = Column(String, nullable=True)  # JSON string
    created_at = Column(DateTime, server_default=func.now())


class K8sUtilization(Base):
    __tablename__ = "k8s_utilization"

    id = Column(String, primary_key=True)  # UUID
    cluster_name = Column(String, nullable=True)
    node_name = Column(String, nullable=False)
    pod_name = Column(String, nullable=True)
    namespace = Column(String, nullable=True)
    cpu_usage = Column(String, nullable=True)
    memory_usage = Column(String, nullable=True)
    recorded_at = Column(DateTime, server_default=func.now())

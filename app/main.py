"""Azure Cost Optimizer — Production API v5.0

Includes:
  - Full Cost Management API (v2024-08-01)
  - All resource type endpoints
  - Optimization Engine with configurable rules
  - Engine config profiles (CRUD)
  - Finding history and remediation tracking
"""
import uuid
import json
import structlog
from fastapi import FastAPI, HTTPException, Query, Depends, Path, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from app.azure_cost import AzureCostClient
from app.azure_resources import AzureResourcesClient
from app.http_client import AzureAPIError
from app.database import get_db, engine
from app.models import Base, CostRecord, K8sUtilization, OptimizationRun, EngineConfig, OptimizationFinding
from app.optimizer.rules import DEFAULT_RULES
from app.optimizer.engine import OptimizationEngine
from app.optimizer.engine_config import get_effective_config, upsert_rule_config, delete_rule_config

Base.metadata.create_all(bind=engine)
log = structlog.get_logger()

app = FastAPI(
    title="Azure Cost Optimizer API",
    version="5.0.0",
    description="Production FinOps platform — real Azure APIs + Optimization Engine",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cost_client     = AzureCostClient()
resource_client = AzureResourcesClient()


@app.exception_handler(AzureAPIError)
async def azure_error_handler(request, exc: AzureAPIError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status,
                        content={"error": {"code": exc.code, "message": exc.message}})


# ─── Schemas ──────────────────────────────────────────────────────────────────
class K8sUtilizationIn(BaseModel):
    cluster_name: Optional[str] = None
    node_name: str
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    cpu_usage: Optional[str] = None
    memory_usage: Optional[str] = None


class RuleConfigIn(BaseModel):
    rule_id:     str = Field(..., description="Rule ID e.g. VM_IDLE, AKS_NO_AUTOSCALER")
    enabled:     bool = True
    overrides:   dict = Field(default_factory=dict, description="Threshold overrides e.g. {cpu_idle_pct: 3.0}")
    description: Optional[str] = None


class AnalyzeRequest(BaseModel):
    subscription_id:  str
    profile:          str  = "default"
    rule_overrides:   dict = Field(default_factory=dict,
        description="Runtime overrides: {\"VM_IDLE\": {\"cpu_idle_pct\": 3.0}}")
    include_metrics:  bool = False
    timespan_metrics: str  = "P7D"


class FindingStatusIn(BaseModel):
    status: str = Field(..., description="open | acknowledged | resolved | ignored")


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    return {"status": 
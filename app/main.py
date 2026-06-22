import uuid
import json
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.azure_cost import AzureCostClient
from app.azure_resources import AzureResourcesClient
from app.database import get_db, engine
from app.models import Base, CostRecord, K8sUtilization

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Azure Cost Optimizer API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cost_client = AzureCostClient()
resource_client = AzureResourcesClient()


class CostResponse(BaseModel):
    id: str
    scope: str
    timeframe: str
    granularity: str
    data: dict


class K8sUtilizationIn(BaseModel):
    cluster_name: Optional[str] = None
    node_name: str
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    cpu_usage: Optional[str] = None
    memory_usage: Optional[str] = None


# ─── Health ──────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ─── Cost endpoints ───────────────────────────────────────────────────────────
@app.get("/costs")
def get_costs(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    granularity: str = Query("Daily"),
    db: Session = Depends(get_db)
):
    try:
        scope = f"/subscriptions/{subscription_id}"
        data = cost_client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
        record = CostRecord(id=str(uuid.uuid4()), subscription_id=subscription_id,
                            timeframe=timeframe, granularity=granularity,
                            raw_response=json.dumps(data))
        db.add(record); db.commit()
        return {"id": record.id, "scope": scope, "timeframe": timeframe, "granularity": granularity, "data": data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/costs/resource-group")
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    granularity: str = Query("Daily"),
    db: Session = Depends(get_db)
):
    try:
        scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        data = cost_client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
        record = CostRecord(id=str(uuid.uuid4()), subscription_id=subscription_id,
                            resource_group=resource_group, timeframe=timeframe,
                            granularity=granularity, raw_response=json.dumps(data))
        db.add(record); db.commit()
        return {"id": record.id, "scope": scope, "data": data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/costs/history")
def cost_history(db: Session = Depends(get_db)):
    records = db.query(CostRecord).order_by(CostRecord.created_at.desc()).limit(100).all()
    return [{"id": r.id, "subscription_id": r.subscription_id,
             "resource_group": r.resource_group, "timeframe": r.timeframe,
             "created_at": str(r.created_at)} for r in records]


# ─── Azure Resources endpoints ────────────────────────────────────────────────
@app.get("/resources/all")
def all_resources(subscription_id: str = Query(...)):
    try:
        return resource_client.list_resources(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/vms")
def list_vms(subscription_id: str = Query(...)):
    try:
        return resource_client.list_vms(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/storage")
def list_storage(subscription_id: str = Query(...)):
    try:
        return resource_client.list_storage_accounts(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/aks")
def list_aks(subscription_id: str = Query(...)):
    try:
        return resource_client.list_aks_clusters(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/appservices")
def list_appservices(subscription_id: str = Query(...)):
    try:
        return resource_client.list_app_services(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/sql")
def list_sql(subscription_id: str = Query(...)):
    try:
        return resource_client.list_sql_servers(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/disks")
def list_disks(subscription_id: str = Query(...)):
    try:
        return resource_client.list_disks(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/keyvaults")
def list_keyvaults(subscription_id: str = Query(...)):
    try:
        return resource_client.list_keyvaults(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/publicips")
def list_publicips(subscription_id: str = Query(...)):
    try:
        return resource_client.list_public_ips(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/resources/resourcegroups")
def list_rgs(subscription_id: str = Query(...)):
    try:
        return resource_client.list_resource_groups(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Kubernetes utilization ───────────────────────────────────────────────────
@app.post("/k8s/utilization")
def save_k8s(payload: K8sUtilizationIn, db: Session = Depends(get_db)):
    record = K8sUtilization(id=str(uuid.uuid4()), **payload.dict())
    db.add(record); db.commit()
    return {"status": "saved", "id": record.id}


@app.get("/k8s/utilization")
def get_k8s(db: Session = Depends(get_db)):
    records = db.query(K8sUtilization).order_by(K8sUtilization.recorded_at.desc()).limit(200).all()
    return [{"id": r.id, "cluster": r.cluster_name, "node": r.node_name,
             "pod": r.pod_name, "namespace": r.namespace,
             "cpu": r.cpu_usage, "memory": r.memory_usage,
             "recorded_at": str(r.recorded_at)} for r in records]

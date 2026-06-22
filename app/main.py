import uuid
import json
from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.azure_cost import AzureCostClient
from app.database import get_db, engine
from app.models import Base, CostRecord, K8sUtilization

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Azure Cost Optimizer API", version="2.0.0")
client = AzureCostClient()


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/costs", response_model=CostResponse)
def get_costs(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    granularity: str = Query("Daily"),
    db: Session = Depends(get_db)
):
    try:
        scope = f"/subscriptions/{subscription_id}"
        data = client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
        record_id = str(uuid.uuid4())
        record = CostRecord(
            id=record_id,
            subscription_id=subscription_id,
            resource_group=None,
            timeframe=timeframe,
            granularity=granularity,
            raw_response=json.dumps(data)
        )
        db.add(record)
        db.commit()
        return CostResponse(id=record_id, scope=scope, timeframe=timeframe, granularity=granularity, data=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/costs/resource-group", response_model=CostResponse)
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    granularity: str = Query("Daily"),
    db: Session = Depends(get_db)
):
    try:
        scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        data = client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
        record_id = str(uuid.uuid4())
        record = CostRecord(
            id=record_id,
            subscription_id=subscription_id,
            resource_group=resource_group,
            timeframe=timeframe,
            granularity=granularity,
            raw_response=json.dumps(data)
        )
        db.add(record)
        db.commit()
        return CostResponse(id=record_id, scope=scope, timeframe=timeframe, granularity=granularity, data=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/costs/history")
def cost_history(db: Session = Depends(get_db)):
    records = db.query(CostRecord).order_by(CostRecord.created_at.desc()).limit(100).all()
    return [{"id": r.id, "subscription_id": r.subscription_id, "resource_group": r.resource_group,
             "timeframe": r.timeframe, "created_at": str(r.created_at)} for r in records]


@app.post("/k8s/utilization")
def save_k8s_utilization(payload: K8sUtilizationIn, db: Session = Depends(get_db)):
    record = K8sUtilization(
        id=str(uuid.uuid4()),
        cluster_name=payload.cluster_name,
        node_name=payload.node_name,
        pod_name=payload.pod_name,
        namespace=payload.namespace,
        cpu_usage=payload.cpu_usage,
        memory_usage=payload.memory_usage
    )
    db.add(record)
    db.commit()
    return {"status": "saved", "id": record.id}


@app.get("/k8s/utilization")
def get_k8s_utilization(db: Session = Depends(get_db)):
    records = db.query(K8sUtilization).order_by(K8sUtilization.recorded_at.desc()).limit(200).all()
    return [{"id": r.id, "cluster": r.cluster_name, "node": r.node_name,
             "pod": r.pod_name, "namespace": r.namespace,
             "cpu": r.cpu_usage, "memory": r.memory_usage,
             "recorded_at": str(r.recorded_at)} for r in records]

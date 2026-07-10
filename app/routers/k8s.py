"""Kubernetes utilization agent endpoints."""
import json
import re
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import K8sUtilization, K8sSnapshot
from app.services.system_settings import get_effective_config as get_system_config
from app.settings import get_settings
from app.user_auth import require_authenticated_user

settings = get_settings()
router = APIRouter(prefix="/k8s", tags=["Kubernetes"])

_ISO8601_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)


class K8sUtilizationIn(BaseModel):
    cluster_name: Optional[str] = None
    node_name: str = Field(..., min_length=1, max_length=253)
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    cpu_usage: Optional[str] = None
    memory_usage: Optional[str] = None


class K8sSnapshotIn(BaseModel):
    cluster_name: str = Field(..., min_length=1, max_length=253)
    collected_at: Optional[str] = None
    summary: dict = Field(default_factory=dict)
    nodes: list[dict] = Field(default_factory=list, max_length=500)
    pods: list[dict] = Field(default_factory=list, max_length=5000)

    @field_validator("collected_at")
    @classmethod
    def _validate_collected_at(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        if not _ISO8601_DATETIME_RE.match(v):
            raise ValueError(
                f"collected_at must be an ISO 8601 datetime (e.g. 2024-01-15T10:30:00Z); got {value!r}"
            )
        return v


def _verify_k8s_agent_token(api_key: Optional[str] = None, db: Optional[Session] = None) -> None:
    k8s_cfg = get_system_config(db, "kubernetes") if db is not None else {}
    expected = k8s_cfg.get("agent_token") or settings.k8s_agent_token
    require = bool(k8s_cfg.get("require_agent_token") or settings.require_k8s_token)
    if settings.is_production and not expected:
        raise HTTPException(status_code=503, detail="K8s agent authentication is not configured")
    if require and not expected:
        raise HTTPException(status_code=503, detail="K8s agent authentication is not configured")
    if not expected:
        if settings.auth_enabled:
            raise HTTPException(status_code=503, detail="K8s agent authentication is not configured")
        return
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _verify_k8s_read_access(request: Request, x_api_key: Optional[str], db: Session) -> None:
    if x_api_key:
        _verify_k8s_agent_token(x_api_key, db)
        return
    if settings.auth_enabled:
        require_authenticated_user(request)
        return
    if settings.is_production:
        raise HTTPException(status_code=401, detail="Sign in required")


@router.post("/utilization", tags=["Kubernetes"])
def save_k8s(
    payload: K8sUtilizationIn,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_agent_token(x_api_key, db)
    record = K8sUtilization(id=str(uuid.uuid4()), **payload.dict())
    db.add(record); db.commit()
    return {"status": "saved", "id": record.id}


@router.post("/snapshot", tags=["Kubernetes"],
          summary="Ingest batched cluster snapshot from utilization agent")
def save_k8s_snapshot(
    payload: K8sSnapshotIn,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_agent_token(x_api_key, db)
    summary = payload.summary or {}
    record = K8sSnapshot(
        id=str(uuid.uuid4()),
        cluster_name=payload.cluster_name,
        node_count=int(summary.get("node_count") or len(payload.nodes)),
        pod_count=int(summary.get("pod_count") or len(payload.pods)),
        payload_json=json.dumps(payload.dict()),
    )
    db.add(record)
    db.commit()
    return {
        "status": "saved",
        "id": record.id,
        "cluster_name": record.cluster_name,
        "node_count": record.node_count,
        "pod_count": record.pod_count,
    }


@router.get("/snapshot", tags=["Kubernetes"],
         summary="Latest cluster snapshot from utilization agent")
def get_k8s_snapshot(
    request: Request,
    cluster_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_read_access(request, x_api_key, db)
    q = db.query(K8sSnapshot).order_by(K8sSnapshot.recorded_at.desc())
    if cluster_name:
        q = q.filter(K8sSnapshot.cluster_name == cluster_name)
    record = q.first()
    if not record:
        raise HTTPException(404, "No snapshot found")
    return {
        "id": record.id,
        "cluster_name": record.cluster_name,
        "node_count": record.node_count,
        "pod_count": record.pod_count,
        "recorded_at": str(record.recorded_at),
        "snapshot": json.loads(record.payload_json or "{}"),
    }


@router.get("/snapshots", tags=["Kubernetes"],
         summary="List recent cluster snapshots")
def list_k8s_snapshots(
    request: Request,
    cluster_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_read_access(request, x_api_key, db)
    q = db.query(K8sSnapshot).order_by(K8sSnapshot.recorded_at.desc())
    if cluster_name:
        q = q.filter(K8sSnapshot.cluster_name == cluster_name)
    records = q.limit(limit).all()
    return [{
        "id": r.id,
        "cluster_name": r.cluster_name,
        "node_count": r.node_count,
        "pod_count": r.pod_count,
        "recorded_at": str(r.recorded_at),
    } for r in records]


@router.get("/utilization", tags=["Kubernetes"])
def get_k8s(
    request: Request,
    cluster_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_read_access(request, x_api_key, db)
    q = db.query(K8sUtilization).order_by(K8sUtilization.recorded_at.desc())
    if cluster_name:
        q = q.filter(K8sUtilization.cluster_name == cluster_name)
    records = q.limit(500).all()
    return [{"id": r.id, "cluster": r.cluster_name, "node": r.node_name,
             "pod": r.pod_name, "namespace": r.namespace,
             "cpu": r.cpu_usage, "memory": r.memory_usage,
             "recorded_at": str(r.recorded_at)}
            for r in records]



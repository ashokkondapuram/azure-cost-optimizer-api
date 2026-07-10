"""Server-sent events — migrated from main.py."""
import json
from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AnalysisJob
from app.user_auth import require_authenticated_user
from app.validators import ensure_subscription_known, require_subscription_id

router = APIRouter(prefix="/events", tags=["Events"])

@router.get("/events/jobs/{subscription_id}", tags=["Events"],
         summary="SSE stream for batch analysis job progress")
async def job_events_stream(
    request: Request,
    subscription_id: str = Path(..., description="Azure subscription ID"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id
    from app.batch_analyzer import expire_stale_analysis_jobs, serialize_job
    from app.job_events import subscribe_job_events

    require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    expire_stale_analysis_jobs(db, subscription_id=sub)

    async def event_generator():
        active = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.subscription_id == sub,
                AnalysisJob.status.in_(["queued", "running"]),
            )
            .order_by(AnalysisJob.created_at.desc())
            .all()
        )
        for job in active:
            payload = json.dumps({"type": "snapshot", "job": serialize_job(job)}, default=str)
            yield f"data: {payload}\n\n"
        async for chunk in subscribe_job_events(sub):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

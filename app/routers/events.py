"""Events router — /events prefix (SSE / webhook endpoints)."""
from fastapi import APIRouter

router = APIRouter(prefix="/events", tags=["Events"])

# Server-sent event and webhook routes live here.
# Currently registered via configure_production_routes(app) in main.py;
# migration to this router is tracked as a follow-up task.

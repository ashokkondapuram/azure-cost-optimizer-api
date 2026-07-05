"""Metrics router — /metrics prefix (Azure Monitor)."""
from fastapi import APIRouter

router = APIRouter(prefix="/metrics", tags=["Monitor"])

# Azure Monitor metric routes are registered via register_azure_live_routes(app)
# in main.py. This stub is here so the router package is complete and ready
# for future extraction.

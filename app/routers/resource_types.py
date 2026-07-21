"""Resource type catalog endpoint."""
from fastapi import APIRouter
from app.resource_type_catalog import resource_types_catalog

router = APIRouter(tags=["Resources"])

@router.get("/resource-types", tags=["Resources"],
         summary="Canonical resource types grouped by category (for cost filters)")
def list_resource_types():
    from app.resource_type_catalog import resource_types_catalog

    return resource_types_catalog()


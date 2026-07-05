"""Routes under /azure/* that always call Azure ARM or Monitor (managed identity token)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session
import structlog

from app.arm_live_reads import fetch_live_resources, wrap_azure_source
from app.database import get_db
from app.db_sync import enrich_aks_arm_clusters
from app.http_client import AzureAPIError
from app.validators import validate_subscription_id
from app.vm_utils import filter_standalone_vms

log = structlog.get_logger(__name__)

AZURE_LIVE_TAG = "Azure Live"


def register_azure_live_routes(
    app: FastAPI,
    resource_client: Any,
    *,
    require_admin_user: Callable[[Request], None],
) -> None:
    """Register live Azure API routes (admin only, uses cached management token)."""

    def _inventory_route(
        path: str,
        resource_type: str,
        summary: str,
        live_fn: Callable[[str], list],
    ) -> None:
        @app.get(
            f"/azure/{path}",
            tags=[AZURE_LIVE_TAG],
            summary=summary,
            name=f"azure_live_{path.replace('/', '_')}",
        )
        def _handler(
            request: Request,
            subscription_id: str = Query(...),
            limit: int | None = Query(None, ge=1, le=200),
            offset: int = Query(0, ge=0),
            db: Session = Depends(get_db),
        ):
            require_admin_user(request)
            sid = validate_subscription_id(subscription_id)
            payload = fetch_live_resources(
                sid, db, resource_client, resource_type,
                lambda: live_fn(sid),
                limit=limit,
                offset=offset,
            )
            return wrap_azure_source(payload, subscription_id=sid)

    _inventory_route(
        "vms",
        "compute/vm",
        "List VMs from Azure Compute API",
        lambda sid: filter_standalone_vms(
            resource_client.list_vms(sid, include_instance_view=False),
        ),
    )
    _inventory_route("vmss", "compute/vmss", "List VM scale sets from Azure", resource_client.list_vm_scale_sets)
    _inventory_route("disks", "compute/disk", "List managed disks from Azure", resource_client.list_disks)
    _inventory_route("snapshots", "compute/snapshot", "List snapshots from Azure", resource_client.list_snapshots)
    _inventory_route("storage", "storage/account", "List storage accounts from Azure", resource_client.list_storage_accounts)
    _inventory_route("appservices", "appservice/webapp", "List App Services from Azure", resource_client.list_app_services)
    _inventory_route("sql", "database/sql", "List SQL servers from Azure", resource_client.list_sql_servers)
    _inventory_route("postgresql", "database/postgresql", "List PostgreSQL servers from Azure", resource_client.list_postgresql_flexible)
    _inventory_route("cosmosdb", "database/cosmosdb", "List Cosmos DB accounts from Azure", resource_client.list_cosmosdb)
    _inventory_route("publicips", "network/publicip", "List public IPs from Azure", resource_client.list_public_ips)
    _inventory_route("loadbalancers", "network/loadbalancer", "List load balancers from Azure", resource_client.list_load_balancers)
    _inventory_route("appgateways", "network/appgateway", "List application gateways from Azure", resource_client.list_application_gateways)
    _inventory_route("nsgs", "network/nsg", "List network security groups from Azure", resource_client.list_network_security_groups)
    _inventory_route("vnets", "network/vnet", "List virtual networks from Azure", resource_client.list_vnets)
    _inventory_route("nics", "network/nic", "List network interfaces from Azure", resource_client.list_network_interfaces)
    _inventory_route("natgateways", "network/nat", "List NAT gateways from Azure", resource_client.list_nat_gateways)
    _inventory_route("privateendpoints", "network/privateendpoint", "List private endpoints from Azure", resource_client.list_private_endpoints)
    _inventory_route("privatelinkservices", "network/privatelinkservice", "List private link services from Azure", resource_client.list_private_link_services)
    _inventory_route("privatedns", "network/privatedns", "List private DNS zones from Azure", resource_client.list_private_dns_zones)
    _inventory_route("keyvaults", "security/keyvault", "List Key Vaults from Azure", resource_client.list_keyvaults)
    _inventory_route("acr", "containers/acr", "List container registries from Azure", resource_client.list_container_registries)

    @app.get(
        "/azure/subscriptions",
        tags=[AZURE_LIVE_TAG],
        summary="List subscriptions from Azure ARM (managed identity token)",
    )
    def azure_subscriptions(request: Request):
        require_admin_user(request)
        try:
            subs = resource_client.list_subscriptions()
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(subs)

    @app.get(
        "/azure/resource-groups",
        tags=[AZURE_LIVE_TAG],
        summary="List resource groups from Azure ARM",
    )
    def azure_resource_groups(
        request: Request,
        subscription_id: str = Query(...),
    ):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            groups = resource_client.list_resource_groups(sid)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(groups, subscription_id=sid)

    @app.get(
        "/azure/resources",
        tags=[AZURE_LIVE_TAG],
        summary="List ARM resources (optional arm_type filter)",
    )
    def azure_resources(
        request: Request,
        subscription_id: str = Query(...),
        arm_type: str | None = Query(
            None,
            description="ARM type e.g. Microsoft.Compute/virtualMachines",
        ),
    ):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            rows = resource_client.list_resources(sid, arm_type)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(rows, subscription_id=sid)

    @app.get(
        "/azure/aks",
        tags=[AZURE_LIVE_TAG],
        summary="List AKS clusters from Azure Container Service API",
    )
    def azure_aks(
        request: Request,
        subscription_id: str = Query(...),
        limit: int | None = Query(None, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)

        def _fetch() -> list:
            clusters = resource_client.list_aks_clusters(sid)
            return enrich_aks_arm_clusters(resource_client, sid, clusters)

        payload = fetch_live_resources(
            sid, db, resource_client, "containers/aks", _fetch,
            limit=limit, offset=offset,
        )
        return wrap_azure_source(payload, subscription_id=sid)

    @app.get(
        "/azure/vms/{resource_group}/{vm_name}",
        tags=[AZURE_LIVE_TAG],
        summary="Get one VM from Azure (instanceView included)",
    )
    def azure_get_vm(
        request: Request,
        resource_group: str = Path(...),
        vm_name: str = Path(...),
        subscription_id: str = Query(...),
    ):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            vm = resource_client.get_vm(sid, resource_group, vm_name)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(vm, subscription_id=sid)

    @app.get(
        "/azure/aks/{resource_group}/{cluster_name}",
        tags=[AZURE_LIVE_TAG],
        summary="Get one AKS cluster from Azure",
    )
    def azure_get_aks(
        request: Request,
        resource_group: str = Path(...),
        cluster_name: str = Path(...),
        subscription_id: str = Query(...),
    ):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            cluster = resource_client.get_aks_cluster(sid, resource_group, cluster_name)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(cluster, subscription_id=sid)

    @app.get(
        "/azure/aks/{resource_group}/{cluster_name}/node-pools",
        tags=[AZURE_LIVE_TAG],
        summary="List AKS node pools from Azure",
    )
    def azure_aks_node_pools(
        request: Request,
        resource_group: str = Path(...),
        cluster_name: str = Path(...),
        subscription_id: str = Query(...),
    ):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            pools = resource_client.list_aks_node_pools(sid, resource_group, cluster_name)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(pools, subscription_id=sid)

    @app.get(
        "/azure/aks/kubernetes-versions",
        tags=[AZURE_LIVE_TAG],
        summary="List supported Kubernetes versions for an Azure region",
    )
    def azure_aks_kubernetes_versions(
        request: Request,
        subscription_id: str = Query(...),
        location: str = Query(...),
        refresh: bool = Query(False),
        db: Session = Depends(get_db),
    ):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        from app.aks_versions import fetch_kubernetes_versions_for_location
        payload = fetch_kubernetes_versions_for_location(
            sid, location, db=db, force_refresh=refresh,
        )
        return wrap_azure_source(payload, subscription_id=sid)

    @app.get(
        "/azure/vnets",
        tags=[AZURE_LIVE_TAG],
        summary="List virtual networks from Azure",
    )
    def azure_vnets(request: Request, subscription_id: str = Query(...)):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            rows = resource_client.list_vnets(sid)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(rows, subscription_id=sid)

    @app.get(
        "/azure/nics",
        tags=[AZURE_LIVE_TAG],
        summary="List network interfaces from Azure",
    )
    def azure_nics(request: Request, subscription_id: str = Query(...)):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            rows = resource_client.list_network_interfaces(sid)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(rows, subscription_id=sid)

    @app.get(
        "/azure/mysql",
        tags=[AZURE_LIVE_TAG],
        summary="List MySQL flexible servers from Azure",
    )
    def azure_mysql(request: Request, subscription_id: str = Query(...)):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            rows = resource_client.list_mysql_flexible(sid)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(rows, subscription_id=sid)

    @app.get(
        "/azure/redis",
        tags=[AZURE_LIVE_TAG],
        summary="List Redis caches from Azure",
    )
    def azure_redis(request: Request, subscription_id: str = Query(...)):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            rows = resource_client.list_redis_caches(sid)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(rows, subscription_id=sid)

    @app.get(
        "/azure/appserviceplans",
        tags=[AZURE_LIVE_TAG],
        summary="List App Service plans from Azure",
    )
    def azure_asp(request: Request, subscription_id: str = Query(...)):
        require_admin_user(request)
        sid = validate_subscription_id(subscription_id)
        try:
            rows = resource_client.list_app_service_plans(sid)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(rows, subscription_id=sid)

    @app.get(
        "/azure/metrics/vm-cpu",
        tags=[AZURE_LIVE_TAG],
        summary="VM CPU and memory metrics from Azure Monitor",
    )
    def azure_vm_cpu_metrics(
        request: Request,
        resource_id: str = Query(..., description="Full ARM resource ID"),
        timespan: str = Query("P7D"),
    ):
        require_admin_user(request)
        try:
            metrics = resource_client.get_vm_cpu_metrics(resource_id, timespan)
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(metrics)

    @app.get(
        "/azure/metrics/resource",
        tags=[AZURE_LIVE_TAG],
        summary="Query Azure Monitor metrics for any ARM resource",
    )
    def azure_resource_metrics(
        request: Request,
        resource_id: str = Query(...),
        metric_names: str = Query(..., description="Comma-separated metric names"),
        timespan: str = Query("PT1H"),
        interval: str = Query("PT5M"),
        aggregation: str = Query("Average"),
        db: Session = Depends(get_db),
    ):
        require_admin_user(request)
        try:
            metrics = resource_client.get_resource_metrics(
                resource_id,
                metric_names=[m.strip() for m in metric_names.split(",") if m.strip()],
                timespan=timespan,
                interval=interval,
                aggregation=aggregation,
                db=db,
            )
        except AzureAPIError as exc:
            raise HTTPException(status_code=503, detail=exc.message) from exc
        return wrap_azure_source(metrics)

    @app.get(
        "/azure/metrics/resource/plan",
        tags=[AZURE_LIVE_TAG],
        summary="Metric names that apply to one resource (by ARM type)",
    )
    def azure_metrics_resource_plan(
        request: Request,
        resource_id: str = Query(..., description="Full ARM resource ID"),
    ):
        require_admin_user(request)
        from app.metrics_api import plan_for_resource
        return plan_for_resource(resource_id)

    @app.get(
        "/azure/metrics/resource/auto",
        tags=[AZURE_LIVE_TAG],
        summary="Fetch Azure Monitor metrics for one resource (profile-driven)",
    )
    def azure_metrics_resource_auto(
        request: Request,
        resource_id: str = Query(..., description="Full ARM resource ID"),
        timespan: str = Query("P7D"),
        db: Session = Depends(get_db),
    ):
        require_admin_user(request)
        from app.metrics_api import fetch_metrics_for_resource
        result = fetch_metrics_for_resource(resource_id, timespan=timespan, db=db)
        if not result.get("ok"):
            raise HTTPException(status_code=404 if "profile" in str(result.get("error", "")).lower() else 503, detail=result)
        return result

    @app.get(
        "/azure/metrics/by-type",
        tags=[AZURE_LIVE_TAG],
        summary="Fetch metrics for all synced resources of one type in a subscription",
    )
    def azure_metrics_by_type(
        request: Request,
        subscription_id: str = Query(...),
        canonical_type: str = Query(..., description="e.g. compute/vm, storage/account"),
        timespan: str = Query("P7D"),
        limit: int = Query(0, ge=0, le=500, description="Max resources per type (0 = all)"),
        db: Session = Depends(get_db),
    ):
        require_admin_user(request)
        from app.metrics_api import fetch_metrics_by_canonical_type
        sid = validate_subscription_id(subscription_id)
        return fetch_metrics_by_canonical_type(
            db, sid, canonical_type.strip().lower(),
            timespan=timespan,
            limit_per_type=limit,
        )

    @app.get(
        "/azure/metrics/subscription",
        tags=[AZURE_LIVE_TAG],
        summary="Fetch metrics for synced inventory (all types or one canonical type)",
    )
    def azure_metrics_subscription(
        request: Request,
        subscription_id: str = Query(...),
        canonical_type: Optional[str] = Query(None, description="Optional filter, e.g. compute/vm"),
        timespan: str = Query("P7D"),
        limit: int = Query(0, ge=0, le=500, description="Max resources per type (0 = all)"),
        db: Session = Depends(get_db),
    ):
        require_admin_user(request)
        from app.metrics_api import fetch_metrics_for_subscription
        sid = validate_subscription_id(subscription_id)
        return fetch_metrics_for_subscription(
            db, sid,
            canonical_type=canonical_type.strip().lower() if canonical_type else None,
            timespan=timespan,
            limit_per_type=limit,
        )

    @app.get(
        "/azure/metrics/profiles",
        tags=[AZURE_LIVE_TAG],
        summary="Catalog of monitor profiles and metric names per ARM resource type",
    )
    def azure_metrics_profiles(request: Request):
        require_admin_user(request)
        from app.metrics_api import monitor_profiles_catalog
        return monitor_profiles_catalog()

    log.info("azure_live_routes_registered")

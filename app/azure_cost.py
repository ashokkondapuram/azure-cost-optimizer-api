"""Azure Cost Management — official API v2024-08-01.

Docs: https://learn.microsoft.com/en-us/rest/api/cost-management/
"""
import structlog
from app.auth import auth_headers
from app.http_client import _post, _get, get_all_pages, BASE

log = structlog.get_logger()

# Latest stable Cost Management API version
COST_API = "2024-08-01"


class AzureCostClient:

    # ------------------------------------------------------------------ #
    #  Core query — wraps POST .../query                                   #
    # ------------------------------------------------------------------ #
    def query_cost(
        self,
        scope: str,
        timeframe: str = "MonthToDate",
        granularity: str = "Daily",
        group_by: list[dict] | None = None,
        filter_obj: dict | None = None,
    ) -> dict:
        """Query actual costs for any ARM scope.

        scope examples:
          /subscriptions/{id}
          /subscriptions/{id}/resourceGroups/{rg}
          /providers/Microsoft.Management/managementGroups/{mg}
        """
        url = f"{BASE}{scope}/providers/Microsoft.CostManagement/query?api-version={COST_API}"

        dataset: dict = {
            "granularity": granularity,
            "aggregation": {
                "totalCost": {"name": "PreTaxCost", "function": "Sum"},
                "totalCostUSD": {"name": "CostUSD", "function": "Sum"},
            },
            "grouping": group_by or [
                {"type": "Dimension", "name": "ResourceGroup"},
                {"type": "Dimension", "name": "ServiceName"},
            ],
        }
        if filter_obj:
            dataset["filter"] = filter_obj

        payload = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": dataset,
        }
        log.info("cost_query", scope=scope, timeframe=timeframe, granularity=granularity)
        return _post(url, auth_headers(), payload)

    # ------------------------------------------------------------------ #
    #  Cost by resource — group by ResourceId                             #
    # ------------------------------------------------------------------ #
    def query_cost_by_resource(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict:
        scope = f"/subscriptions/{subscription_id}"
        return self.query_cost(
            scope=scope,
            timeframe=timeframe,
            granularity="None",
            group_by=[
                {"type": "Dimension", "name": "ResourceId"},
                {"type": "Dimension", "name": "ResourceType"},
                {"type": "Dimension", "name": "ResourceGroup"},
                {"type": "Dimension", "name": "ServiceName"},
            ],
        )

    # ------------------------------------------------------------------ #
    #  Cost by service — group by ServiceName                             #
    # ------------------------------------------------------------------ #
    def query_cost_by_service(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict:
        scope = f"/subscriptions/{subscription_id}"
        return self.query_cost(
            scope=scope,
            timeframe=timeframe,
            granularity="None",
            group_by=[
                {"type": "Dimension", "name": "ServiceName"},
                {"type": "Dimension", "name": "ServiceTier"},
            ],
        )

    # ------------------------------------------------------------------ #
    #  Cost budget — GET budgets list                                     #
    # ------------------------------------------------------------------ #
    def list_budgets(self, subscription_id: str) -> list:
        url = (
            f"{BASE}/subscriptions/{subscription_id}"
            f"/providers/Microsoft.CostManagement/budgets?api-version={COST_API}"
        )
        data = _get(url, auth_headers())
        return data.get("value", [])

    # ------------------------------------------------------------------ #
    #  Forecast — POST .../forecast                                       #
    # ------------------------------------------------------------------ #
    def query_forecast(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict:
        scope = f"/subscriptions/{subscription_id}"
        url = f"{BASE}{scope}/providers/Microsoft.CostManagement/forecast?api-version={COST_API}"
        payload = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": {
                "granularity": "Daily",
                "aggregation": {
                    "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                },
            },
            "includeActualCost": True,
            "includeFreshPartialCost": False,
        }
        log.info("cost_forecast", subscription_id=subscription_id)
        return _post(url, auth_headers(), payload)

    # ------------------------------------------------------------------ #
    #  Dimensions — GET available dimensions for UI filters               #
    # ------------------------------------------------------------------ #
    def list_dimensions(self, subscription_id: str) -> list:
        url = (
            f"{BASE}/subscriptions/{subscription_id}"
            f"/providers/Microsoft.CostManagement/dimensions?api-version={COST_API}"
        )
        data = _get(url, auth_headers())
        return data.get("value", [])

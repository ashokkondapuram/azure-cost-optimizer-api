from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.azure_cost import AzureCostClient

app = FastAPI(title="Azure Cost Optimizer API", version="1.0.0")
client = AzureCostClient()


class CostResponse(BaseModel):
    scope: str
    timeframe: str
    granularity: str
    data: dict


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/costs", response_model=CostResponse)
def get_costs(
    subscription_id: str = Query(..., description="Azure subscription ID"),
    timeframe: str = Query("MonthToDate", description="Billing timeframe"),
    granularity: str = Query("Daily", description="Granularity: Daily or None")
):
    try:
        scope = f"/subscriptions/{subscription_id}"
        data = client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
        return CostResponse(scope=scope, timeframe=timeframe, granularity=granularity, data=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/costs/resource-group", response_model=CostResponse)
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    granularity: str = Query("Daily")
):
    try:
        scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        data = client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
        return CostResponse(scope=scope, timeframe=timeframe, granularity=granularity, data=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

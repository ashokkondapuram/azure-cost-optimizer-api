# Azure Cost Optimizer API

A minimal FastAPI backend for Azure cost visibility using Managed Identity and least-privilege RBAC.

## Prerequisites
- Python 3.11+
- Azure subscription with Cost Management data access
- Managed Identity enabled on the hosting resource (App Service, Container Apps, VM, AKS workload identity, etc.)
- RBAC role assignment: `Cost Management Reader`

## Local development
Local development can use Azure CLI authentication through `DefaultAzureCredential`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Test the API:
```bash
curl "http://127.0.0.1:8000/costs?subscription_id=<subscription-id>"
curl "http://127.0.0.1:8000/costs/resource-group?subscription_id=<subscription-id>&resource_group=<rg-name>"
```

## Azure deployment
1. Deploy the FastAPI app to Azure App Service, Azure Container Apps, or AKS.
2. Enable a system-assigned or user-assigned managed identity.
3. Assign `Cost Management Reader` at the smallest required scope.
4. Verify the app can request a token for `https://management.azure.com/.default`.
5. Call the `/costs` endpoints from your frontend or internal systems.

## Endpoints
- `GET /health` - health check.
- `GET /costs` - subscription-level costs.
- `GET /costs/resource-group` - resource-group-level costs.

## Notes
- Cost Management API availability can vary by account type and permissions.
- Add pagination, richer filters, and stronger auth before production use.

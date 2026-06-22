# Azure Cost Optimizer API

This project provides a Python FastAPI service that fetches Azure Cost Management data through Azure Resource Manager APIs using Managed Identity. It is designed for least-privilege access so the application can read cost data without broader subscription permissions.

## Architecture
- FastAPI exposes REST endpoints for cost queries.
- Azure Managed Identity authenticates the app without storing secrets.
- `DefaultAzureCredential` obtains tokens from the managed identity in Azure-hosted environments.
- The API calls Azure Cost Management query endpoints through `management.azure.com`.

## Azure permissions
Assign the managed identity at the narrowest scope possible:
- Preferred: Resource group scope when only resource-group level reporting is needed.
- Otherwise: Subscription scope for subscription-wide cost reporting.

Minimum RBAC role:
- `Cost Management Reader`

Optional supporting roles, only if required by your implementation:
- `Reader` on the same scope if you also need ARM metadata beyond cost query responses.

## Example role assignment
```bash
az role assignment create \
  --assignee <managed-identity-principal-id> \
  --role "Cost Management Reader" \
  --scope /subscriptions/<subscription-id>
```

For resource-group-only scope:
```bash
az role assignment create \
  --assignee <managed-identity-principal-id> \
  --role "Cost Management Reader" \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>
```

## Security notes
- No client secrets or connection strings are required.
- Disable interactive credentials in production.
- Restrict network exposure using private ingress or IP restrictions where possible.
- Add API authentication in front of FastAPI if the service is exposed beyond internal callers.
- Log request IDs and Azure API failures, but avoid logging tokens or sensitive billing exports.

## Suggested next steps
- Add response caching for repeated dashboard queries.
- Add filters for service name, tags, and date ranges.
- Add a React frontend that calls this API to render dashboards and optimization recommendations.

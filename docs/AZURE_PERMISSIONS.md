# Required Azure RBAC Permissions

## Minimum Role Assignments

Assign these at **subscription scope** (or Management Group for multi-sub):

| Role | Purpose |
|------|---------|
| `Cost Management Reader` | Read Cost Management queries, budgets, forecasts |
| `Reader` | Read all resource metadata via ARM |
| `Monitoring Reader` | Read Azure Monitor metrics for utilization-based rules |

## Service Principal Setup

```bash
# 1. Create App Registration
az ad app create --display-name "azure-cost-optimizer"

# 2. Create Service Principal
az ad sp create --id <app-id>

# 3. Assign Cost Management Reader
az role assignment create \
  --assignee <sp-object-id> \
  --role "Cost Management Reader" \
  --scope /subscriptions/<subscription-id>

# 4. Assign Reader
az role assignment create \
  --assignee <sp-object-id> \
  --role "Reader" \
  --scope /subscriptions/<subscription-id>

# 5. Assign Monitoring Reader (metrics for utilization rules)
az role assignment create \
  --assignee <sp-object-id> \
  --role "Monitoring Reader" \
  --scope /subscriptions/<subscription-id>

# 6. Create client secret
az ad app credential reset --id <app-id> --years 1
```

## Environment Variables

Set in `.env` or Azure App Service configuration:

```
AZURE_TENANT_ID=<tenant-id>
AZURE_CLIENT_ID=<client-id>
AZURE_CLIENT_SECRET=<secret>
DATABASE_URL=postgresql://...
```

## Cost Management API Scopes

| Scope | Example |
|-------|---------|
| Subscription | `/subscriptions/{id}` |
| Resource Group | `/subscriptions/{id}/resourceGroups/{rg}` |
| Management Group | `/providers/Microsoft.Management/managementGroups/{mg}` |

## Cost currency fields (Azure only — no app-side FX)

| Azure field | Meaning |
|-------------|---------|
| `PreTaxCost` | Charge in **billing currency** (e.g. CAD for Canadian subscriptions) |
| `CostUSD` | Same charge in **USD**, provided by Azure |
| `Currency` | Billing currency code (`CAD`, `USD`, …) |

Use `GET /costs/summary?subscription_id=...` for subscription totals in both amounts.

App endpoint `GET /costs/summary` aggregates `PreTaxCost` + `CostUSD` from Cost Management API `2024-08-01`.

## API Versions Used

| API | Version |
|-----|---------|
| Cost Management | `2024-08-01` |
| ARM Resources | `2024-03-01` |
| Compute VMs | `2024-03-01` |
| Resource SKUs | `2021-07-01` |
| AKS | `2024-02-01` |
| Storage | `2023-05-01` |
| App Service | `2023-12-01` |
| SQL | `2023-08-01-preview` |
| PostgreSQL Flexible | `2023-12-01-preview` |
| MySQL Flexible | `2023-12-30` |
| Cosmos DB | `2024-05-15` |
| Key Vault | `2023-07-01` |
| Networking | `2024-01-01` |
| Azure Monitor Metrics | `2023-10-01` |

# Azure Cost Optimizer API - Architecture

## Overview
FastAPI backend deployed as an Azure Web App, backed by Azure Database for PostgreSQL Flexible Server. A lightweight Kubernetes agent pod pushes node and pod utilization data to the API periodically.

## Components

### Azure Web App
- Hosts the FastAPI application on Linux App Service Plan (B1 or higher).
- System-assigned Managed Identity enabled - no client secrets needed.
- `DATABASE_URL` is injected as an App Setting (not in code).

### Azure Database for PostgreSQL Flexible Server
- Stores cost records and Kubernetes utilization records.
- Tables: `cost_records`, `k8s_utilization`.
- Connection uses SSL (`sslmode=require`).
- Firewall restricted to the Web App outbound IPs.

### Kubernetes Utilization Agent
- A single lightweight Deployment in the `monitoring` namespace.
- Uses `python:3.11-alpine` for minimal image size.
- Runs with a dedicated `ServiceAccount` bound to a `ClusterRole` that only allows `get` and `list` on `nodes` and `pods` resources - least privilege.
- Calls metrics-server to collect CPU and memory usage.
- Pushes data to the FastAPI `/k8s/utilization` endpoint every 60 seconds.
- Resource limits: 100m CPU, 128Mi memory.

## Managed Identity and RBAC
- Web App Managed Identity should be assigned `Cost Management Reader` at subscription or resource group scope.
- No other Azure roles are needed for basic cost fetching.
- Kubernetes RBAC is enforced through ClusterRole with minimal verbs.

## Deployment steps

### 1. Deploy Azure infrastructure
```bash
az group create --name cost-optimizer-rg --location canadacentral
az deployment group create \
  --resource-group cost-optimizer-rg \
  --template-file infra/webapp.bicep \
  --parameters postgresAdminPassword=<strong-password>
```

### 2. Assign Cost Management Reader to Web App Managed Identity
```bash
WEBAPP_PRINCIPAL=$(az webapp identity show --name azure-cost-optimizer --resource-group cost-optimizer-rg --query principalId -o tsv)
az role assignment create \
  --assignee $WEBAPP_PRINCIPAL \
  --role "Cost Management Reader" \
  --scope /subscriptions/<subscription-id>
```

### 3. Deploy FastAPI app to Web App
```bash
zip -r app.zip app/ requirements.txt
az webapp deployment source config-zip \
  --resource-group cost-optimizer-rg \
  --name azure-cost-optimizer \
  --src app.zip
```

### 4. Deploy Kubernetes agent
```bash
kubectl create namespace monitoring
# Update API_URL in k8s/utilization-agent.yaml to your Web App URL
kubectl apply -f k8s/utilization-agent.yaml
```

## Security notes
- PostgreSQL credentials are passed at deploy time and stored as Web App settings, not in code.
- No secrets in the repository.
- Kubernetes agent uses in-cluster service account token only - no external credentials.
- Consider Azure Private Link for PostgreSQL in production.
- Add API key or Azure AD authentication in front of the FastAPI endpoints for production use.

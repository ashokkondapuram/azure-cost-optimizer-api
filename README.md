# Azure Cost Optimizer

Full-stack Azure cost and resource visibility tool.

- **Backend**: Python FastAPI on Azure Web App
- **Database**: Azure PostgreSQL Flexible Server
- **Auth**: Azure Managed Identity + Cost Management Reader (least privilege)
- **Frontend**: React with Recharts
- **K8s Agent**: Lightweight pod (python:3.11-alpine) that pushes node/pod utilization to the API

## Repository structure

```
azure-cost-optimizer-api/
├── app/
│   ├── main.py               # FastAPI routes (costs, resources, k8s)
│   ├── azure_cost.py         # Azure Cost Management API client
│   ├── azure_resources.py    # All Azure resource type clients
│   ├── database.py           # SQLAlchemy + PostgreSQL
│   └── models.py             # ORM models
├── frontend/
│   ├── src/
│   │   ├── App.js            # Router + sidebar
│   │   ├── api/client.js     # Axios API calls
│   │   └── pages/
│   │       ├── Dashboard.js  # Cost bar chart
│   │       ├── Resources.js  # All Azure resource types table
│   │       ├── K8sPage.js    # Node + pod utilization
│   │       └── CostHistory.js# Stored cost query log
│   └── package.json
├── infra/
│   └── webapp.bicep          # Azure Web App + PostgreSQL Bicep
├── k8s/
│   ├── utilization-agent.yaml
│   └── agent.py
└── docs/
    ├── README.md
    └── architecture.md
```

## Azure Resources covered

| Endpoint | Resource Type |
|---|---|
| `/resources/all` | All ARM resources |
| `/resources/vms` | Virtual Machines |
| `/resources/aks` | AKS Clusters |
| `/resources/storage` | Storage Accounts |
| `/resources/appservices` | App Services / Web Apps |
| `/resources/sql` | SQL Servers |
| `/resources/disks` | Managed Disks |
| `/resources/keyvaults` | Key Vaults |
| `/resources/publicips` | Public IP Addresses |
| `/resources/resourcegroups` | Resource Groups |

## Required Azure RBAC (Managed Identity)

| Role | Scope | Purpose |
|---|---|---|
| Cost Management Reader | Subscription | Read cost data |
| Reader | Subscription | Read all ARM resource metadata |

## Local development

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
cp .env.example .env   # set REACT_APP_API_URL
npm install
npm start
```

## Azure deployment

1. Deploy infra: `az deployment group create --template-file infra/webapp.bicep`
2. Assign Managed Identity roles (Cost Management Reader + Reader)
3. Deploy backend via zip deploy or GitHub Actions
4. Build frontend: `npm run build` → deploy `build/` to Azure Static Web Apps or serve via Web App
5. Deploy K8s agent: `kubectl apply -f k8s/utilization-agent.yaml`

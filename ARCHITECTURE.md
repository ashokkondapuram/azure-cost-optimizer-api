# CostOptimizeRecommender
## System Architecture Document

**Version:** 1.0
**Date:** July 2026
**Audience:** Development Team, Stakeholders, New Team Members

---

## Executive Summary

CostOptimizeRecommender is an enterprise FinOps platform designed to provide organizations with centralized Azure cost visibility, resource inventory management, and actionable optimization recommendations. The platform integrates with Azure Cost Management APIs and Azure Resource Manager to deliver real-time cost insights and optimization guidance grounded in actual billed costs.

The system follows a modern three-tier architecture with a React-based frontend, FastAPI backend, and PostgreSQL database persistence. It supports optional Kubernetes telemetry through an in-cluster agent and provides enterprise-grade security with JWT authentication and role-based access control.

---

## System Overview

### Business Purpose

The platform serves organizations requiring:

- Centralized Azure cost visibility and budget tracking
- Comprehensive inventory coverage across major Azure resource types
- Actionable optimization recommendations with estimated savings
- Secure JWT-based authentication with role-based access control
- Historical data persistence for trending and analysis
- FinOps portal for cost exploration and recommendations

---

## Architecture Overview

### Three-Tier Architecture

The platform implements a classic three-tier architecture:

| Layer | Description |
|-------|-------------|
| **Presentation Layer** | React SPA providing user interface for cost exploration, inventory management, and recommendations |
| **Application Layer** | FastAPI backend providing REST APIs, business logic, Azure integrations, and optimization engine |
| **Data Layer** | PostgreSQL database for persistent storage of costs, inventory, findings, and operational data |

### Frontend Architecture

**Technology Stack:**
- React (modern UI framework)
- Node.js 18+ for build tooling
- CSS and modern CSS frameworks
- React Context for state management
- Custom hooks for reusable logic

**Key Features:**
- Navigation driven by appRegistry.js configuration
- Dashboard for cost overview and KPIs
- Cost Explorer for time-series analysis
- Resource Inventory pages for each Azure resource type
- Recommendations page displaying optimization findings
- Admin tools for optimization runs, engine configuration, settings, and user management

### Backend Architecture

**Technology Stack:**
- Python 3.13 with FastAPI framework
- SQLAlchemy 2.0 for ORM and database abstraction
- PostgreSQL for persistent data storage
- Alembic for database migrations
- Uvicorn as ASGI server
- Azure SDK libraries for API integration

---

## Core Components

### Azure Integration Layer

#### Cost Management Integration

Queries Azure Cost Management API (v2024-08-01) for actual billed costs using Managed Identity. Retrieves cost data at subscription and resource-group levels with support for multiple time periods and filtering options.

#### Azure Resource Manager Integration

Enumerates and inventories Azure resources across major types: VMs, disks, AKS clusters, storage accounts, databases, networking, App Service, Key Vault, and aggregate page resources. Supports both live queries and cached data from PostgreSQL.

### Optimization Engine

A configurable rule-based analysis system that evaluates Azure resources against defined optimization policies. Key features:

- Rule-based findings with configurable thresholds
- Savings estimates derived from actual billed cost baselines
- Per-resource type sub-engines for specialized analysis
- Configurable engine profiles enabling/disabling rules
- Finding history tracking and remediation status management
- Findings deduplication to eliminate redundant recommendations

### Authentication & Authorization

JWT-based authentication system with the following characteristics:

- Token-based access at /api/auth/login endpoint
- Rate limiting on login endpoint
- Role-based access control (Admin and Viewer roles)
- Admin-gated endpoints: /optimize/analyze, /sync, /optimize, /dashboard
- Subscription-scoped access for multi-tenant deployments
- Secure settings encryption at rest in production
- Kubernetes agent authentication via shared secret token

### Database Schema

PostgreSQL database manages the following primary entities:

| Entity | Purpose |
|--------|---------|
| **CostRecord** | Stores Azure cost data snapshots from Cost Management API |
| **Resource Inventory** | Cached Azure resource inventory snapshots for fast retrieval |
| **OptimizationFinding** | Optimization findings with savings estimates and remediation status |
| **OptimizationRun** | History of optimization analysis runs with execution details |
| **EngineConfig** | Optimization engine configuration including enabled rules and thresholds |
| **K8sUtilization** | Kubernetes cluster utilization snapshots from in-cluster agent |
| **SubscriptionCache** | Cached subscription metadata and access information |
| **AnalysisJob** | Background job tracking for long-running analysis operations |

### Kubernetes Telemetry Agent

An optional lightweight in-cluster polling agent that:

- Reads node and pod utilization metrics from metrics-server
- Sends utilization snapshots to the backend API
- Uses token-based authentication for secure communication
- Deployable as Kubernetes Pod via utilization-agent.yaml

---

## Data Flow Architecture

### Cost Data Pipeline

```
Azure Cost Management API → Backend Cost Service → PostgreSQL → Frontend Cost Explorer
```

The system retrieves actual billed costs from Azure, normalizes the data, stores snapshots in PostgreSQL for historical analysis, and exposes via REST APIs to the frontend for visualization and exploration.

### Resource Inventory Pipeline

```
Azure Resource Manager → Backend Resource Service → PostgreSQL → Frontend Inventory Pages
```

Resource enumeration can be performed either as live queries to ARM or from cached inventory snapshots. The sync service updates the database periodically, enabling fast list views and filtered searches in the UI.

### Optimization Analysis Pipeline

```
Cost + Inventory Data → Optimization Engine → Findings → PostgreSQL → Recommendations API → Frontend UI
```

The optimization engine analyzes combined cost and inventory data against configured rules, generates findings with savings estimates, deduplicates results, persists to the database, and exposes via the recommendations endpoint for frontend display.

### Kubernetes Telemetry Pipeline

```
Kubernetes Cluster → In-Cluster Agent → Backend API → PostgreSQL
```

The optional K8s agent polls metrics-server for node and pod utilization metrics, converts to snapshots, and POSTs to the backend with token-based authentication. Data is stored for trend analysis and cost allocation insights.

---

## Technology Stack

| Layer | Technology | Version/Details |
|-------|-----------|-----------------|
| **Frontend** | React | Single Page Application |
| **Frontend Build** | Node.js | v18 with npm |
| **Backend** | FastAPI | v0.111.0 |
| **Server** | Uvicorn | ASGI application server |
| **Language** | Python | v3.13 |
| **Database** | PostgreSQL | Relational database |
| **ORM** | SQLAlchemy | v2.0.36 |
| **Migrations** | Alembic | v1.13.1 |
| **Authentication** | PyJWT | v2.8.0 JWT token support |
| **Azure SDKs** | Multiple | azure-identity, azure-storage-blob |
| **Validation** | Pydantic | v2.10.6 |
| **HTTP Client** | httpx | v0.27.0 with HTTP/2 |
| **Caching** | cachetools | v5.3.3 |
| **Logging** | structlog | v24.1.0 |
| **Encryption** | cryptography | v42.0.8 |
| **Retry Logic** | tenacity | v8.3.0 |

---

## Deployment & Infrastructure

### Azure App Service Deployment

Primary deployment target is Azure App Service (Linux runtime) with the following configuration:

- Runtime: Python 3.13 on Linux
- Oryx build system enabled for automatic dependency installation
- Startup command: uvicorn app.main:app with configured port
- Health check endpoint: /health/live
- Frontend built during CI/CD and served as static files
- Environment configuration via App Service settings
- Deployment via Azure Pipelines with zip deploy

### Docker Containerization

Multi-stage Dockerfile provides containerized deployment option:

- Stage 1: React frontend build (Node 18 base)
- Stage 2: Python runtime with frontend artifacts
- Final image exposes port 8000
- Non-root app user for security
- Health check configured

### Kubernetes Deployment

Kubernetes configuration files in /k8s/ directory support:

- Deployment manifests for main application
- In-cluster telemetry agent deployment
- Service definitions for networking
- ConfigMaps for configuration management
- Secrets for sensitive credentials

### CI/CD Pipeline

Azure Pipelines orchestrates the deployment process:

- Triggered on commits to main and feature branches
- Build stage: Compiles React frontend, runs tests
- Artifact creation: Zips application with built frontend
- Deploy stage: Configures App Service and deploys zip
- Integration with terraform-connect for infrastructure updates

---

## Security Architecture

### Authentication

The platform implements JWT-based authentication with these characteristics:

- Login endpoint at /api/auth/login requires credentials
- JWT tokens issued with configurable expiration
- Rate limiting prevents brute force attacks
- Tokens validated on protected endpoints
- JWT_SECRET stored securely in production environments

### Authorization

Role-based access control restricts sensitive operations:

- Admin role required for: optimization analysis, data sync, settings, user management
- Viewer role for read-only access to dashboards and reports
- Subscription-scoped access for multi-tenant environments

### Azure Integration Security

Azure API access uses secure managed identity authentication:

- Managed Identity via DefaultAzureCredential for passwordless auth
- RBAC roles: Cost Management Reader, Resource Manager Reader
- Subscription-level scoping prevents cross-subscription access

### Data Protection

Sensitive data protection mechanisms include:

- Settings encryption at rest using SETTINGS_ENCRYPTION_KEY
- Database connections over secure connections
- K8s agent token-based authentication
- Environment variable-based secrets management

### CORS & Network Security

Network security is enforced through:

- Dynamic CORS middleware restricts frontend origins
- CORS_ALLOWED_ORIGINS configurable via environment variables
- HTTP security headers enforced

---

## External Integration Points

| Service | Purpose | Authentication |
|---------|---------|-----------------|
| **Azure Cost Management API** | Retrieve billed cost data | Managed Identity |
| **Azure Resource Manager** | Enumerate resources | Managed Identity |
| **Kubernetes API** | Metrics collection (optional) | Service Account |
| **PostgreSQL** | Data persistence | Connection string |

---

## Environment Configuration

Key environment variables control system behavior:

| Variable | Purpose | Production Required |
|----------|---------|-------------------|
| **DATABASE_URL** | PostgreSQL connection string | Yes |
| **AUTH_ENABLED** | Enable JWT authentication | Yes (true) |
| **JWT_SECRET** | JWT token signing key | Yes |
| **SETTINGS_ENCRYPTION_KEY** | Encrypts sensitive settings | Yes |
| **K8S_AGENT_TOKEN** | K8s agent shared secret | Yes (if agent deployed) |
| **CORS_ALLOWED_ORIGINS** | CORS allowed origins | Yes |
| **APP_ENV** | Environment: dev, qa, prod | Yes (prod) |
| **REACT_APP_API_URL** | Frontend API URL | Frontend only |

---

## Deployment Requirements

### Azure Prerequisites

- Azure subscription with sufficient credits
- App Service resource group created
- PostgreSQL flexible server or equivalent database
- Managed Identity assigned to App Service
- Azure Pipelines project with build/deploy configuration
- Azure Cost Management Reader and Reader roles assigned to identity

### CI/CD Requirements

- GitHub or Azure Repos repository configured
- Azure Pipelines configured with azure-pipelines.yml
- Service connection to Azure subscription
- Build agent with Node.js 18+ and Python 3.13
- Artifact storage for build outputs

### Post-Deployment Configuration

- Configure environment variables in App Service settings
- Set DATABASE_URL pointing to PostgreSQL instance
- Initialize database schema via Alembic migrations
- Create initial admin user
- Verify API health check endpoint
- Configure frontend API_URL to backend endpoint

---

## Performance & Scalability

### Caching Strategy

The system implements multiple caching layers:

- Database query caching with SQLAlchemy
- HTTP cache control headers for static assets
- Resource inventory snapshots reduce ARM API calls
- Cost data batching and pagination support
- LRU caching for frequently accessed data

### Scalability Considerations

Horizontal scaling supported through:

- Stateless FastAPI design enables multiple backend instances
- Azure App Service auto-scaling rules can distribute load
- PostgreSQL connection pooling via SQLAlchemy
- Frontend SPA can scale to serve more concurrent users
- Pagination support prevents loading large result sets
- Asynchronous background task processing available

---

## Monitoring & Observability

### Health Checks

Health check endpoint /health/live provides liveness probe for orchestration platforms. Docker and Kubernetes use this endpoint to determine service health.

### Logging

Structured logging via structlog provides:

- Request/response logging for API calls
- Database query logging in development
- Error tracking with context
- Performance metrics
- Structured log format for easy parsing and analysis

---

## Repository Structure

```
CostOptimizeRecommender/
├── app/                           # Backend FastAPI application
│   ├── main.py                   # Entry point with API routes
│   ├── analysis/                 # DB analysis orchestration
│   ├── optimizer/                # Optimization engine
│   ├── resources/                # Per-type resource handling
│   ├── dashboard/                # Dashboard API
│   ├── models.py                 # SQLAlchemy ORM models
│   ├── database.py               # Database configuration
│   ├── auth.py                   # Authentication logic
│   ├── middleware/               # CORS, auth middleware
│   └── ...                       # Additional service modules
│
├── frontend/                      # React single-page application
│   ├── public/
│   ├── src/
│   │   ├── App.js               # Main React component
│   │   ├── api/                 # API client code
│   │   ├── components/          # Reusable React components
│   │   ├── pages/               # Page components
│   │   ├── hooks/               # Custom React hooks
│   │   ├── context/             # React Context
│   │   ├── styles/              # CSS files
│   │   ├── utils/               # Utility functions
│   │   └── config/              # Frontend configuration
│   ├── package.json
│   └── package-lock.json
│
├── k8s/                          # Kubernetes manifests
│   ├── agent.py                 # K8s telemetry agent
│   ├── utilization-agent.yaml   # Agent deployment
│   └── ...                      # Other K8s resources
│
├── docs/                         # Additional documentation
│   ├── FUNCTIONALITY.md         # Feature documentation
│   ├── DEPLOY_APP_SERVICE.md   # Deployment guide
│   ├── security.md              # Security details
│   └── ...
│
├── tests/                        # Test suite
├── scripts/                      # Utility scripts
├── data/                         # Data files
├── specs/                        # Specifications
│
├── requirements.txt             # Python dependencies
├── requirements-dev.txt         # Development dependencies
├── Dockerfile                   # Container image definition
├── docker-ignore                # Docker build exclusions
├── azure-pipelines.yml          # CI/CD configuration
├── alembic.ini                  # Database migration config
├── README.md                    # Project overview
├── ARCHITECTURE.md              # This file
└── .env.example                 # Environment template
```

---

## Key Modules & Services

### Backend Core Modules

**app/main.py**
- FastAPI application initialization
- API route definitions
- Middleware setup (auth, CORS)
- Health check endpoints

**app/optimizer/**
- Optimization engine implementation
- Rule-based analysis logic
- Finding generation and deduplication
- Engine configuration management

**app/resources/**
- Per-resource type handlers
- Azure Resource Manager integration
- Resource inventory management
- Metrics and specifications per resource type

**app/analysis/**
- Database analysis orchestration
- Batch analysis job management
- Historical trend analysis

**app/dashboard/**
- Dashboard API endpoints
- KPI calculations
- Summary statistics

**app/auth.py**
- JWT token generation and validation
- Authentication middleware
- Rate limiting

**app/database.py**
- SQLAlchemy engine and session management
- Connection pooling
- Migration framework integration

### Frontend Core Modules

**frontend/src/api/**
- API client implementation
- HTTP request helpers
- Error handling

**frontend/src/pages/**
- Dashboard page
- Cost Explorer page
- Resource Inventory pages
- Recommendations page
- Admin pages

**frontend/src/components/**
- Reusable UI components
- Charts and visualizations
- Tables and data grids
- Forms and inputs

**frontend/src/hooks/**
- Custom React hooks
- Data fetching logic
- State management helpers

**frontend/src/config/appRegistry.js**
- Navigation configuration
- Route definitions
- Feature flags

---

## Data Model Relationships

### Key Entity Relationships

**Cost Records** ← → **Subscriptions**
- Cost data belongs to specific subscriptions
- Multiple cost records per subscription over time

**Resources** ← → **Cost Records**
- Resources can be associated with cost allocations
- Cost data aggregated across resources

**Optimization Findings** ← → **Resources**
- Findings are specific to individual resources
- Multiple findings possible per resource

**Optimization Runs** ← → **Findings**
- Runs generate sets of findings
- Findings tracked to their originating run

**Engine Config** ← → **Optimization Runs**
- Configuration used during run execution
- Configuration changes tracked with runs

---

## API Overview

### Authentication
- `POST /api/auth/login` - User login, JWT token issuance

### Cost Management
- `GET /api/costs/summary` - Cost summary for period
- `GET /api/costs/by-service` - Cost breakdown by service
- `GET /api/costs/by-resource` - Cost by individual resource
- `GET /api/costs/daily` - Daily cost trends
- `GET /api/costs/by-resource-group` - Cost by resource group

### Resource Management
- `GET /api/resources` - List resources with pagination
- `GET /api/resources/{id}` - Get resource details
- `GET /api/resources/{type}` - List resources by type
- `POST /api/sync` - Trigger resource sync (admin only)

### Optimization
- `POST /api/optimize/analyze` - Run optimization analysis (admin only)
- `GET /api/optimize/findings` - List optimization findings
- `GET /api/optimize/findings/{id}` - Finding details
- `PUT /api/optimize/findings/{id}` - Update finding status
- `GET /api/optimize/config` - Get engine configuration (admin only)
- `PUT /api/optimize/config` - Update engine configuration (admin only)

### Dashboard
- `GET /api/dashboard` - Dashboard overview
- `GET /api/dashboard/top-spend` - Top spending resources
- `GET /api/dashboard/trends` - Cost trends

### Kubernetes (if agent enabled)
- `POST /api/k8s/utilization` - Submit utilization snapshot (agent only)
- `GET /api/k8s/utilization` - Query utilization data

### Health & Status
- `GET /health/live` - Liveness probe
- `GET /api/status` - System status

---

## Development Workflow

### Local Development

1. Clone repository
2. Create virtual environment: `python -m venv .venv`
3. Activate environment: `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements-dev.txt`
5. Set up .env file from .env.example
6. Run database migrations: `alembic upgrade head`
7. Start backend: `uvicorn app.main:app --reload`
8. In another terminal, start frontend: `cd frontend && npm start`

### Testing

- Backend: `pytest tests/`
- Frontend: `cd frontend && npm test`
- Integration: Docker Compose setup for full stack testing

### Building for Production

- Docker: `docker build -t cost-optimize:latest .`
- Azure Pipelines: Automatic build on git push to main branch

---

## Troubleshooting & Common Issues

### Database Connection Issues
- Verify DATABASE_URL format
- Check PostgreSQL is accessible
- Review firewall rules for App Service

### Authentication Failures
- Verify JWT_SECRET is set and consistent
- Check token expiration settings
- Validate CORS_ALLOWED_ORIGINS configuration

### Azure Integration Issues
- Verify Managed Identity has correct roles
- Check subscription is accessible
- Review Azure API rate limits

### Performance Degradation
- Check database connection pool utilization
- Review query execution times
- Validate caching effectiveness
- Monitor App Service CPU and memory

---

## Future Enhancements

- Advanced cost allocation and chargeback
- ML-based cost prediction
- Multi-cloud support (AWS, GCP)
- Real-time alert system
- Cost anomaly detection
- Custom report generation
- Budget forecasting
- Reserved Instance optimization recommendations

---

## Conclusion

CostOptimizeRecommender is a well-architected enterprise platform that combines modern full-stack technologies with cloud-native deployment patterns. The system emphasizes security through JWT authentication and RBAC, scalability through stateless design and caching, and operational excellence through structured logging and health checks. The modular architecture allows for independent scaling of frontend, backend, and data layers, while the optional Kubernetes integration extends capabilities for containerized environments.

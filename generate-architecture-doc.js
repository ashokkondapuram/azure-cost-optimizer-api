const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, AlignmentType,
        BorderStyle, WidthType, ShadingType, HeadingLevel, PageBreak, PageOrientation } = require('docx');
const fs = require('fs');

// Define borders for tables
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

// Helper to create a heading
const createHeading = (text, level = 1) => {
  const sizes = { 1: 32, 2: 28, 3: 24 };
  return new Paragraph({
    heading: level === 1 ? HeadingLevel.HEADING_1 : level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3,
    children: [new TextRun({ text, bold: true, size: sizes[level] * 2 })],
    spacing: { before: level === 1 ? 240 : 180, after: 180 }
  });
};

// Helper to create body text
const createText = (text, options = {}) => {
  return new Paragraph({
    children: [new TextRun({ text, ...options })],
    spacing: { after: 120 }
  });
};

// Helper to create a code/diagram block
const createDiagram = (text) => {
  return new Paragraph({
    children: [new TextRun({ text, font: "Courier New", size: 20, color: "2E75B6" })],
    spacing: { after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" } }
  });
};

// Helper to create table
const createTable = (headers, rows, columnWidths = null) => {
  const tableWidth = 9360; // Full content width
  const defaultWidths = columnWidths || headers.map(() => tableWidth / headers.length);

  const headerCells = headers.map((header, idx) =>
    new TableCell({
      borders,
      width: { size: defaultWidths[idx], type: WidthType.DXA },
      shading: { fill: "2E75B6", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        children: [new TextRun({ text: header, bold: true, color: "FFFFFF" })]
      })]
    })
  );

  const dataCells = rows.map(row =>
    new TableRow({
      children: row.map((cell, idx) =>
        new TableCell({
          borders,
          width: { size: defaultWidths[idx], type: WidthType.DXA },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun(cell)] })]
        })
      )
    })
  );

  return new Table({
    width: { size: tableWidth, type: WidthType.DXA },
    columnWidths: defaultWidths,
    rows: [
      new TableRow({ children: headerCells }),
      ...dataCells
    ]
  });
};

// Content sections
const sections = [{
  properties: {
    page: {
      size: {
        width: 12240,   // US Letter
        height: 15840
      },
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } // 1 inch margins
    }
  },
  children: [
    // ===== TITLE PAGE =====
    new Paragraph({
      children: [new TextRun("")],
      spacing: { after: 480 }
    }),
    new Paragraph({
      children: [new TextRun({ text: "TECHNICAL ARCHITECTURE", size: 40, bold: true, color: "1F4E78" })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 }
    }),
    new Paragraph({
      children: [new TextRun({ text: "CostOptimizeRecommender Platform", size: 32, bold: true })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 }
    }),
    new Paragraph({
      children: [new TextRun({ text: "Comprehensive System Design & Component Documentation", size: 24, italic: true })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 480 }
    }),
    new Paragraph({
      children: [new TextRun("")],
      spacing: { after: 240 }
    }),
    new Paragraph({
      children: [new TextRun({ text: "Version: 2.0", size: 24 })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 }
    }),
    new Paragraph({
      children: [new TextRun({ text: "Date: July 2026", size: 24 })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 }
    }),
    new Paragraph({
      children: [new TextRun({ text: "Enterprise FinOps Platform with Azure Integration", size: 22, italic: true })],
      alignment: AlignmentType.CENTER
    }),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== EXECUTIVE SUMMARY =====
    createHeading("Executive Summary"),
    createText("CostOptimizeRecommender is an enterprise FinOps platform designed to provide organizations with centralized Azure cost visibility, resource inventory management, and actionable optimization recommendations. The platform integrates seamlessly with Azure Cost Management APIs and Azure Resource Manager to deliver real-time cost insights grounded in actual billed costs."),
    createText("The system implements a modern three-tier architecture with:"),
    createText("• React-based Single Page Application (SPA) frontend", { size: 22 }),
    createText("• FastAPI REST API backend with enterprise features", { size: 22 }),
    createText("• PostgreSQL relational database for persistent storage", { size: 22 }),
    createText("• Optional Kubernetes telemetry integration for utilization insights", { size: 22 }),
    createText("• JWT-based authentication with role-based access control (RBAC)", { size: 22 }),
    createText("• Historical data persistence for trending and advanced analysis", { size: 22 }),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== SYSTEM ARCHITECTURE OVERVIEW =====
    createHeading("System Architecture Overview"),

    createHeading("1. Three-Tier Architecture Model", 2),
    createDiagram(`
    ┌─────────────────────────────────────────────────────────────┐
    │                   PRESENTATION LAYER                          │
    │              React SPA Frontend (Node.js)                    │
    │  Dashboard | Cost Explorer | Inventory | Recommendations   │
    └──────────────────────────┬──────────────────────────────────┘
                               │ REST API / JSON
    ┌──────────────────────────▼──────────────────────────────────┐
    │               APPLICATION LAYER                              │
    │     FastAPI Backend (Python 3.13 + Uvicorn)                │
    │  Cost Service | Resource Service | Optimization Engine     │
    │  Authentication | Authorization | Business Logic           │
    └──────────────────────────┬──────────────────────────────────┘
                               │ SQL Queries
    ┌──────────────────────────▼──────────────────────────────────┐
    │                  DATA LAYER                                  │
    │              PostgreSQL Database                            │
    │  Cost Records | Resources | Findings | Configurations      │
    └─────────────────────────────────────────────────────────────┘
    `),

    createText("Each layer is independently scalable and can be deployed on separate infrastructure:"),
    createText("• Frontend: Served as static files via CDN or App Service", { size: 22 }),
    createText("• Backend: Stateless FastAPI servers enable horizontal scaling", { size: 22 }),
    createText("• Database: PostgreSQL with connection pooling for concurrent access", { size: 22 }),

    new Paragraph({ children: [new TextRun("")] }),

    createHeading("2. Core System Components", 2),
    createDiagram(`
    ┌────────────────────────────────────────────────────────────────┐
    │                        EXTERNAL SYSTEMS                         │
    │  Azure Cost Management | Azure Resource Manager | K8s Cluster  │
    └──────────────────────────────┬─────────────────────────────────┘
                                   │
    ┌──────────────────────────────▼─────────────────────────────────┐
    │                      BACKEND API GATEWAY                        │
    │  Authentication | Authorization | Request Routing | CORS       │
    └──────────────┬──────────────────────────┬──────────────────────┘
                   │                          │
    ┌──────────────▼──────────────┐  ┌───────▼─────────────────────┐
    │   COST SERVICE              │  │  RESOURCE SERVICE           │
    │ • Fetch costs from Azure    │  │ • Inventory all resources   │
    │ • Normalize cost data       │  │ • Live ARM queries          │
    │ • Store cost snapshots      │  │ • Cache management          │
    │ • Cost analysis & trends    │  │ • Resource categorization   │
    └──────────────┬──────────────┘  └───────┬─────────────────────┘
                   │                          │
    ┌──────────────▼──────────────┐  ┌───────▼─────────────────────┐
    │  OPTIMIZATION ENGINE        │  │  DATABASE SERVICE           │
    │ • Rule-based analysis       │  │ • SQLAlchemy ORM            │
    │ • Savings calculations      │  │ • Query optimization        │
    │ • Finding generation        │  │ • Connection pooling        │
    │ • Deduplication logic       │  │ • Migration management      │
    └──────────────┬──────────────┘  └───────┬─────────────────────┘
                   │                          │
                   └──────────────┬───────────┘
                                  │
                    ┌─────────────▼────────────┐
                    │   PostgreSQL Database    │
                    │  (Persistent Storage)    │
                    └──────────────────────────┘
    `),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== DATA FLOW DIAGRAMS =====
    createHeading("Data Flow Architecture"),

    createHeading("Cost Data Pipeline", 2),
    createDiagram(`
    ┌──────────────────────┐
    │ Azure Cost           │
    │ Management API       │
    │ (v2024-08-01)        │
    └──────────┬───────────┘
               │ Query costs for subscriptions
               │ (Timeframe, ResourceGroup filter)
    ┌──────────▼──────────────────┐
    │ Cost Fetch Service           │
    │ • Validate subscription      │
    │ • Normalize cost data        │
    │ • Aggregate costs            │
    └──────────┬───────────────────┘
               │ Cost Record objects
    ┌──────────▼──────────────────┐
    │ PostgreSQL Database          │
    │ - CostRecord table           │
    │ - Indexed by subscription    │
    │ - Historical snapshots       │
    └──────────┬───────────────────┘
               │ SQL query results
    ┌──────────▼──────────────────┐
    │ REST API Endpoint            │
    │ GET /api/costs/summary       │
    │ GET /api/costs/by-service    │
    └──────────┬───────────────────┘
               │ JSON response
    ┌──────────▼──────────────────┐
    │ React Frontend               │
    │ • Cost Explorer Charts       │
    │ • Dashboard KPIs             │
    │ • Trend Analysis             │
    └──────────────────────────────┘
    `),

    createHeading("Resource Inventory Pipeline", 2),
    createDiagram(`
    ┌──────────────────────┐
    │ Azure Resource       │
    │ Manager API          │
    │ (Live enumeration)   │
    └──────────┬───────────┘
               │ List resources by type
               │ • VMs, Disks, AKS
               │ • Storage, DBs, Networking
    ┌──────────▼────────────────────┐
    │ Resource Discovery Service     │
    │ • Enumerate all resource types │
    │ • Fetch resource properties    │
    │ • Extract metadata             │
    └──────────┬────────────────────┘
               │ Resource objects
    ┌──────────▼────────────────────┐
    │ Resource Enrichment Module     │
    │ • Categorize resources         │
    │ • Link to cost data            │
    │ • Calculate metrics            │
    └──────────┬────────────────────┘
               │ Enriched resources
    ┌──────────▼────────────────────┐
    │ PostgreSQL Database            │
    │ - Resource Inventory Tables    │
    │ - Index by type, subscription  │
    │ - Cached snapshots             │
    └──────────┬────────────────────┘
               │ Query results
    ┌──────────▼────────────────────┐
    │ REST API Endpoints             │
    │ GET /api/resources/{type}      │
    │ GET /api/resources/{id}        │
    └──────────┬────────────────────┘
               │ JSON response
    ┌──────────▼────────────────────┐
    │ React Frontend                 │
    │ • Resource Inventory Pages     │
    │ • Filtered Search              │
    │ • Resource Details             │
    └────────────────────────────────┘
    `),

    createHeading("Optimization Analysis Pipeline", 2),
    createDiagram(`
    ┌─────────────────────────────────────┐
    │ Admin: Trigger Optimization Run     │
    │ POST /api/optimize/analyze          │
    └──────────────┬──────────────────────┘
                   │
    ┌──────────────▼──────────────────────┐
    │ Optimization Engine                 │
    │ • Load configuration rules           │
    │ • Fetch cost data from DB            │
    │ • Fetch resource inventory from DB   │
    └──────────────┬──────────────────────┘
                   │
    ┌──────────────▼──────────────────────────────┐
    │ Analysis Execution                          │
    │ For each resource type:                     │
    │  • Apply specialized sub-engine             │
    │  • Evaluate against rules (CPU, disk, etc) │
    │  • Calculate savings estimates              │
    │  • Generate findings                        │
    └──────────────┬──────────────────────────────┘
                   │
    ┌──────────────▼──────────────────────────────┐
    │ Finding Deduplication                       │
    │ • Hash findings for uniqueness               │
    │ • Merge similar findings                     │
    │ • Track remediation status                   │
    └──────────────┬──────────────────────────────┘
                   │
    ┌──────────────▼──────────────────────────────┐
    │ PostgreSQL Database                         │
    │ - OptimizationFinding table                 │
    │ - OptimizationRun table (history)          │
    │ - Finding status & evidence                 │
    └──────────────┬──────────────────────────────┘
                   │
    ┌──────────────▼──────────────────────────────┐
    │ REST API Endpoint                           │
    │ GET /api/optimize/findings                  │
    │ GET /api/optimize/findings/{id}             │
    └──────────────┬──────────────────────────────┘
                   │
    ┌──────────────▼──────────────────────────────┐
    │ React Frontend                              │
    │ • Recommendations Page                      │
    │ • Savings Summary                           │
    │ • Finding Details & Evidence                │
    └─────────────────────────────────────────────┘
    `),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== TECHNOLOGY STACK =====
    createHeading("Technology Stack"),

    createTable(
      ["Component", "Technology", "Version", "Purpose"],
      [
        ["Frontend Framework", "React", "18.x", "Single Page Application (SPA)"],
        ["Build Tool", "Node.js / npm", "18.x", "Frontend build and package management"],
        ["Styling", "CSS3", "Modern", "Responsive design and styling"],
        ["Backend Framework", "FastAPI", "0.111+", "REST API with async support"],
        ["Server", "Uvicorn", "Latest", "ASGI application server"],
        ["Language", "Python", "3.13", "Backend development language"],
        ["Database", "PostgreSQL", "13+", "Relational data storage"],
        ["ORM", "SQLAlchemy", "2.0.36", "Database abstraction layer"],
        ["Migrations", "Alembic", "1.13.1", "Database schema versioning"],
        ["Authentication", "PyJWT", "2.8.0", "JWT token signing & validation"],
        ["Validation", "Pydantic", "2.10.6", "Data validation & serialization"],
        ["HTTP Client", "httpx", "0.27.0", "Async HTTP requests (HTTP/2)"],
        ["Azure SDK", "azure-identity", "Latest", "Managed Identity authentication"],
        ["Caching", "cachetools", "5.3.3", "LRU caching for performance"],
        ["Logging", "structlog", "24.1.0", "Structured logging framework"],
        ["Encryption", "cryptography", "42.0.8", "Settings encryption at rest"],
        ["Retry Logic", "tenacity", "8.3.0", "Resilient API calls with backoff"]
      ],
      [2500, 2200, 1500, 2760]
    ),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== COMPONENT DETAILS =====
    createHeading("Core Components in Detail"),

    createHeading("Frontend Components", 2),
    createDiagram(`
    ┌─────────────────────────────────────────┐
    │         React Frontend (SPA)             │
    ├─────────────────────────────────────────┤
    │  Pages:                                 │
    │  • Dashboard (KPI overview)             │
    │  • Cost Explorer (time-series)          │
    │  • Resource Inventory (VM, Disk, AKS...) │
    │  • Recommendations (findings display)   │
    │  • Admin Tools (config, sync, users)    │
    ├─────────────────────────────────────────┤
    │  Components:                            │
    │  • Charts & Graphs (cost trends)        │
    │  • Data Tables (sortable, filterable)   │
    │  • Forms (input validation)             │
    │  • Navigation (appRegistry-driven)      │
    ├─────────────────────────────────────────┤
    │  State Management:                      │
    │  • React Context (auth, user)           │
    │  • Custom Hooks (data fetching)         │
    │  • Local storage (preferences)          │
    ├─────────────────────────────────────────┤
    │  API Client:                            │
    │  • RESTful HTTP calls                   │
    │  • JWT token handling                   │
    │  • Error handling & retries             │
    └─────────────────────────────────────────┘
    `),

    createHeading("Backend API Services", 2),
    createDiagram(`
    ┌───────────────────────────────────────────────┐
    │          FastAPI Application                  │
    │  (Uvicorn ASGI Server on Port 8000)          │
    ├───────────────────────────────────────────────┤
    │  Authentication Layer:                        │
    │  • POST /api/auth/login - JWT issuance       │
    │  • Rate limiting (prevent brute force)        │
    │  • Token validation middleware                │
    ├───────────────────────────────────────────────┤
    │  Cost Management Service:                     │
    │  • GET /api/costs/summary                     │
    │  • GET /api/costs/by-service                  │
    │  • GET /api/costs/daily (trending)            │
    │  • GET /api/costs/by-resource-group          │
    ├───────────────────────────────────────────────┤
    │  Resource Management Service:                 │
    │  • GET /api/resources (paginated)             │
    │  • GET /api/resources/{type} (filtered)       │
    │  • GET /api/resources/{id} (detail view)      │
    │  • POST /api/sync (admin: refresh inventory)  │
    ├───────────────────────────────────────────────┤
    │  Optimization Service:                        │
    │  • POST /api/optimize/analyze (admin)         │
    │  • GET /api/optimize/findings                 │
    │  • PUT /api/optimize/findings/{id}            │
    │  • GET/PUT /api/optimize/config (admin)       │
    ├───────────────────────────────────────────────┤
    │  Dashboard Service:                           │
    │  • GET /api/dashboard (overview KPIs)         │
    │  • GET /api/dashboard/top-spend               │
    │  • GET /api/dashboard/trends                  │
    ├───────────────────────────────────────────────┤
    │  Kubernetes Integration (optional):           │
    │  • POST /api/k8s/utilization (agent submit)   │
    │  • GET /api/k8s/utilization (query data)      │
    ├───────────────────────────────────────────────┤
    │  System Health:                               │
    │  • GET /health/live (liveness probe)          │
    │  • GET /api/status (detailed status)          │
    └───────────────────────────────────────────────┘
    `),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== DATABASE SCHEMA =====
    createHeading("Database Schema (PostgreSQL)"),
    createDiagram(`
    ┌─────────────────────────────────────┐
    │       PostgreSQL Database            │
    ├─────────────────────────────────────┤
    │  Core Tables:                       │
    │                                     │
    │  CostRecord:                        │
    │  • subscription_id (FK)             │
    │  • resource_group                   │
    │  • service_name                     │
    │  • cost_amount                      │
    │  • currency                         │
    │  • timeframe (daily/hourly)         │
    │  • timestamp                        │
    │                                     │
    │  Resource (Inventory):              │
    │  • resource_id (PK)                 │
    │  • subscription_id (FK)             │
    │  • resource_group                   │
    │  • resource_type                    │
    │  • name                             │
    │  • properties (JSON)                │
    │  • tags (JSON)                      │
    │  • location                         │
    │  • last_updated                     │
    │                                     │
    │  OptimizationFinding:               │
    │  • finding_id (PK)                  │
    │  • resource_id (FK)                 │
    │  • rule_id                          │
    │  • finding_type                     │
    │  • title & description              │
    │  • estimated_savings                │
    │  • status (open/remediated/ignored) │
    │  • evidence (JSON)                  │
    │  • created_at, updated_at           │
    │                                     │
    │  OptimizationRun:                   │
    │  • run_id (PK)                      │
    │  • subscription_id (FK)             │
    │  • start_time, end_time             │
    │  • findings_count                   │
    │  • total_savings                    │
    │  • status                           │
    │                                     │
    │  EngineConfig:                      │
    │  • config_id (PK)                   │
    │  • enabled_rules (JSON)             │
    │  • rule_thresholds (JSON)           │
    │  • version                          │
    │  • created_at                       │
    │                                     │
    │  K8sUtilization:                    │
    │  • utilization_id (PK)              │
    │  • cluster_name                     │
    │  • node_metrics (JSON)              │
    │  • pod_metrics (JSON)               │
    │  • timestamp                        │
    │                                     │
    │  AnalysisJob:                       │
    │  • job_id (PK)                      │
    │  • status (queued/running/complete) │
    │  • progress_percent                 │
    │  • result (JSON)                    │
    │  • created_at, completed_at         │
    └─────────────────────────────────────┘
    `),

    createHeading("Database Relationships", 2),
    createDiagram(`
    ┌──────────────┐         ┌─────────────────┐
    │ Subscription │◄────────│  CostRecord     │
    │              │         │ (1 subscription │
    │              │         │  to many costs) │
    └──────────────┘         └─────────────────┘
           ▲
           │
           │
           │
    ┌──────┴───────┐         ┌─────────────────┐
    │   Resource   │◄────────│  OptimizationFinding
    │ (Inventory)  │         │ (1 resource to │
    │              │         │  many findings) │
    └──────────────┘         └─────────────────┘
           ▲
           │
           │
           ├─────────────────────────────┐
           │                             │
    ┌──────┴──────────┐          ┌──────▼──────────┐
    │ OptimizationRun │          │  EngineConfig   │
    │ (historical)    │          │ (rules & config)│
    └─────────────────┘          └─────────────────┘
    `),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== SECURITY ARCHITECTURE =====
    createHeading("Security Architecture"),

    createHeading("Authentication Flow", 2),
    createDiagram(`
    ┌──────────────────────┐
    │  User/Client         │
    │  (Frontend App)      │
    └──────────┬───────────┘
               │
               │ POST /api/auth/login
               │ (username, password)
               ▼
    ┌──────────────────────────────────────┐
    │  Authentication Service              │
    │  • Validate credentials              │
    │  • Check rate limit (max attempts)   │
    │  • Generate JWT token                │
    └──────────┬───────────────────────────┘
               │
               │ JWT Token Response
               │ (exp, role, subscription)
               ▼
    ┌──────────────────────────────────────┐
    │  Client Storage                      │
    │  • Store JWT in localStorage/memory  │
    │  • Include in Authorization header   │
    └──────────┬───────────────────────────┘
               │
               │ GET /api/resources
               │ Header: Authorization: Bearer {JWT}
               ▼
    ┌──────────────────────────────────────┐
    │  Request Middleware                  │
    │  • Extract JWT from header           │
    │  • Verify signature (JWT_SECRET)     │
    │  • Validate expiration               │
    │  • Check subscription scope          │
    └──────────┬───────────────────────────┘
               │
               ├─ Invalid? ──→ 401 Unauthorized
               │
               └─ Valid? ──→ Continue to route handler
    `),

    createHeading("Authorization Model (RBAC)", 2),
    createText("The system implements two-tier role-based access control:"),
    createText("", { size: 20 }),

    createTable(
      ["Role", "Permissions", "Protected Endpoints"],
      [
        ["Admin", "Read/Write all data. Execute analysis. Manage configs. Create users.", "/api/optimize/analyze, /api/sync, /api/optimize/config, /api/settings"],
        ["Viewer", "Read-only access to dashboards and reports. Cannot execute changes.", "/api/costs/*, /api/resources/*, /api/optimize/findings (read-only)"]
      ],
      [1400, 3800, 3760]
    ),

    createHeading("Azure Integration Security", 2),
    createDiagram(`
    ┌─────────────────────────────────────┐
    │  Backend Service                    │
    │  (Running in Azure App Service)     │
    ├─────────────────────────────────────┤
    │  Managed Identity (System-assigned) │
    │  • Passwordless authentication      │
    │  • Uses Azure metadata service      │
    │  • DefaultAzureCredential in SDK    │
    └──────────┬──────────────────────────┘
               │
               │ Automatic token acquisition
               │ (from Azure metadata service)
               ▼
    ┌──────────────────────────────────────┐
    │  Azure RBAC Roles (per identity):    │
    │  • Cost Management Reader            │
    │    └─ Read costs from Cost Mgmt API  │
    │  • Reader                            │
    │    └─ Enumerate resources via ARM    │
    └──────────┬───────────────────────────┘
               │
               │ OAuth 2.0 token
               ▼
    ┌──────────────────────────────────────┐
    │  Azure APIs                          │
    │  • Cost Management API               │
    │  • Resource Manager API              │
    │  • Monitor API (metrics)             │
    └──────────────────────────────────────┘
    `),

    createHeading("Data Protection", 2),
    createText("Sensitive data is protected through:"),
    createText("• Settings Encryption: Settings marked as sensitive are encrypted at rest using SETTINGS_ENCRYPTION_KEY (AES-256)", { size: 22 }),
    createText("• Database Security: PostgreSQL connections use SSL/TLS, credentials stored in environment variables", { size: 22 }),
    createText("• K8s Agent Token: Shared secret token-based authentication for optional Kubernetes telemetry agent", { size: 22 }),
    createText("• JWT Secret: Cryptographically signed tokens with expiration, stored securely in production", { size: 22 }),
    createText("• CORS Control: Dynamic CORS middleware validates frontend origin from CORS_ALLOWED_ORIGINS", { size: 22 }),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== DEPLOYMENT ARCHITECTURE =====
    createHeading("Deployment Architecture"),

    createHeading("Azure App Service Deployment", 2),
    createDiagram(`
    ┌──────────────────────────────────────────────────┐
    │         Azure App Service (Linux)                │
    │         Python 3.13 Runtime                      │
    ├──────────────────────────────────────────────────┤
    │  Startup Configuration:                          │
    │  • Oryx build system (auto-installs deps)        │
    │  • Startup command:                              │
    │    uvicorn app.main:app --host 0.0.0.0 --port 8000 │
    │                                                   │
    │  Health Check:                                   │
    │  • Endpoint: /health/live                        │
    │  • Interval: 60 seconds                          │
    │  • Failure threshold: 3 attempts                 │
    ├──────────────────────────────────────────────────┤
    │  Configuration (App Service settings):           │
    │  • DATABASE_URL (PostgreSQL connection)          │
    │  • AUTH_ENABLED (true in production)             │
    │  • JWT_SECRET (secure random key)                │
    │  • SETTINGS_ENCRYPTION_KEY (AES-256 key)        │
    │  • CORS_ALLOWED_ORIGINS (frontend URLs)         │
    │  • APP_ENV (prod/qa/dev)                         │
    ├──────────────────────────────────────────────────┤
    │  Frontend Serving:                               │
    │  • Built React SPA in /app/static/               │
    │  • Served by FastAPI SPA route handler           │
    │  • Cache control headers (static assets)         │
    ├──────────────────────────────────────────────────┤
    │  Scaling:                                        │
    │  • Horizontal: Multiple instances (stateless)    │
    │  • Auto-scale based on CPU/memory metrics        │
    │  • Database connection pooling                   │
    └──────────────────────────────────────────────────┘
    `),

    createHeading("Docker Containerization", 2),
    createDiagram(`
    ┌────────────────────────────────────────────────────┐
    │          Multi-Stage Dockerfile                    │
    ├────────────────────────────────────────────────────┤
    │                                                    │
    │  Stage 1: Frontend Build                          │
    │  ┌──────────────────────────────────────────────┐ │
    │  │ FROM node:18 as frontend-build               │ │
    │  │ COPY frontend/ .                             │ │
    │  │ RUN npm ci && npm run build                  │ │
    │  │ Output: /app/build (dist files)              │ │
    │  └──────────────────────────────────────────────┘ │
    │                                                    │
    │  Stage 2: Python Runtime                          │
    │  ┌──────────────────────────────────────────────┐ │
    │  │ FROM python:3.13-slim                        │ │
    │  │ COPY requirements.txt .                      │ │
    │  │ RUN pip install -r requirements.txt          │ │
    │  │ COPY app/ ./app/                             │ │
    │  │ COPY --from=frontend-build /app/build        │ │
    │  │       ./app/static/                          │ │
    │  │                                               │ │
    │  │ USER app (non-root)                          │ │
    │  │ EXPOSE 8000                                  │ │
    │  │ HEALTHCHECK: /health/live                    │ │
    │  │ CMD: uvicorn app.main:app ...                │ │
    │  └──────────────────────────────────────────────┘ │
    │                                                    │
    │  Final Image: cost-optimize:latest                │
    │  • ~600MB (slim Python + dependencies)            │
    │  • Non-root user for security                     │
    │  • Health check configured                        │
    └────────────────────────────────────────────────────┘
    `),

    createHeading("CI/CD Pipeline (Azure Pipelines)", 2),
    createDiagram(`
    ┌──────────────┐
    │ Git Push     │
    │ (main/feat)  │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────────────────┐
    │ Azure Pipelines Trigger      │
    │ (azure-pipelines.yml)        │
    └──────┬───────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────┐
    │ Build Stage:                             │
    │ • Checkout code                          │
    │ • Build frontend (React -> dist/)         │
    │ • Run tests (backend/frontend)           │
    │ • Create deployment package (zip)        │
    │ • Publish artifacts                      │
    └──────┬───────────────────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────┐
    │ Deploy Stage:                            │
    │ • Download artifacts                     │
    │ • Configure App Service (settings)       │
    │ • Run Alembic migrations (schema)        │
    │ • Deploy zip to App Service              │
    │ • Run smoke tests                        │
    └──────┬───────────────────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────┐
    │ Azure App Service Live                   │
    │ (New version running)                    │
    └──────────────────────────────────────────┘
    `),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== KUBERNETES INTEGRATION =====
    createHeading("Kubernetes Integration (Optional)"),

    createHeading("Telemetry Agent Deployment", 2),
    createDiagram(`
    ┌──────────────────────────────────────────────┐
    │         Kubernetes Cluster                   │
    ├──────────────────────────────────────────────┤
    │                                              │
    │  ┌──────────────────────────────────────┐   │
    │  │  In-Cluster Agent Pod                │   │
    │  │  (utilization-agent.yaml)            │   │
    │  ├──────────────────────────────────────┤   │
    │  │  Image: cost-optimize-agent:latest   │   │
    │  │  ServiceAccount: k8s-agent           │   │
    │  │                                       │   │
    │  │  Periodic Job (every 5 minutes):     │   │
    │  │  1. Query metrics-server             │   │
    │  │  2. Collect node metrics             │   │
    │  │  3. Collect pod metrics              │   │
    │  │  4. Build utilization snapshot       │   │
    │  │  5. POST to backend /api/k8s/util... │   │
    │  │     (with K8S_AGENT_TOKEN auth)      │   │
    │  └─────────────┬──────────────────────┘   │
    │                │ HTTPS                    │
    └────────────────┼───────────────────────────┘
                     │
                     ▼
    ┌──────────────────────────────────────────┐
    │  Backend API (in App Service)            │
    │  POST /api/k8s/utilization               │
    │  • Validate K8S_AGENT_TOKEN              │
    │  • Parse metrics                         │
    │  • Store in K8sUtilization table         │
    └──────────────────────────────────────────┘
                     │
                     ▼
    ┌──────────────────────────────────────────┐
    │  PostgreSQL Database                     │
    │  K8sUtilization table                    │
    │  • cluster_name                          │
    │  • node_metrics (JSON)                   │
    │  • pod_metrics (JSON)                    │
    │  • timestamp                             │
    └──────────────────────────────────────────┘
    `),

    createHeading("Agent Pod Specification", 2),
    createDiagram(`
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: cost-optimize-agent
      namespace: kube-system
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: cost-optimize-agent
      template:
        metadata:
          labels:
            app: cost-optimize-agent
        spec:
          serviceAccountName: k8s-agent
          containers:
          - name: agent
            image: cost-optimize-agent:latest
            env:
            - name: BACKEND_API_URL
              value: "https://your-app.azurewebsites.net"
            - name: K8S_AGENT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: agent-token
                  key: token
            - name: POLL_INTERVAL
              value: "300"  # 5 minutes
            resources:
              requests:
                memory: "64Mi"
                cpu: "50m"
              limits:
                memory: "256Mi"
                cpu: "200m"
    `),

    createHeading("Agent Responsibilities", 2),
    createText("The Kubernetes telemetry agent performs the following tasks:"),
    createText("", { size: 20 }),

    createTable(
      ["Task", "Frequency", "Data Collected", "Sent To"],
      [
        ["Node Metrics", "Every 5 min", "CPU usage, Memory usage, Disk capacity", "K8sUtilization table"],
        ["Pod Metrics", "Every 5 min", "Pod CPU, Pod Memory per namespace", "K8sUtilization table"],
        ["Cluster Discovery", "Every hour", "Node count, total capacity", "K8sUtilization table"],
        ["Metrics Query", "On-demand", "Query historical metrics", "Backend /api/k8s/utilization GET"]
      ],
      [1500, 1500, 3000, 2360]
    ),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== PERFORMANCE & SCALABILITY =====
    createHeading("Performance & Scalability"),

    createHeading("Caching Strategy", 2),
    createDiagram(`
    ┌────────────────────────────────────────────────────┐
    │          Multi-Layer Caching Strategy              │
    ├────────────────────────────────────────────────────┤
    │                                                    │
    │  Layer 1: Database Query Caching                  │
    │  • SQLAlchemy query result caching                │
    │  • Connection pooling (5-20 connections)          │
    │  • Index optimization on cost/resource tables     │
    │                                                    │
    │  Layer 2: Application-Level Caching               │
    │  • LRU cache for frequently accessed data         │
    │  • cachetools library (TTL cache)                 │
    │  • Cache duration: 5-60 minutes (configurable)    │
    │                                                    │
    │  Layer 3: Resource Snapshot Caching               │
    │  • Resource inventory snapshots in DB             │
    │  • Reduces ARM API calls (quota limited)          │
    │  • Hourly refresh via sync service                │
    │                                                    │
    │  Layer 4: HTTP Cache Control                      │
    │  • Static assets: Cache-Control: max-age=31536000 │
    │  • API responses: Cache-Control: max-age=300      │
    │  • Etag support for conditional requests          │
    │                                                    │
    │  Layer 5: Frontend Browser Cache                  │
    │  • React SPA bundle caching                       │
    │  • Service Worker for offline capability          │
    │  • Local storage for user preferences             │
    │                                                    │
    └────────────────────────────────────────────────────┘
    `),

    createHeading("Horizontal Scalability", 2),
    createDiagram(`
    ┌─────────────────────────────────────────────────┐
    │     Load Balancer / Azure Front Door             │
    │     (Distribute traffic)                         │
    └────────────────┬────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ Backend │ │ Backend │ │ Backend │
    │Instance │ │Instance │ │Instance │
    │   #1    │ │   #2    │ │   #3    │
    │         │ │         │ │         │
    │ Stateless │ Stateless │ Stateless
    │ FastAPI │ │ FastAPI │ │ FastAPI │
    └────┬────┘ └────┬────┘ └────┬────┘
         │           │           │
         └───────────┼───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  PostgreSQL Database  │
         │  Connection Pool:     │
         │  • 5-20 per instance  │
         │  • pgBouncer (if HPA) │
         └───────────────────────┘

    Scaling Triggers:
    • CPU > 70% → add instance
    • Memory > 80% → add instance
    • Response time > 2s → add instance
    • Cooldown: 5 minutes between scaling events
    `),

    createHeading("Performance Metrics", 2),
    createText("Target SLOs for production deployment:"),
    createText("", { size: 20 }),

    createTable(
      ["Metric", "Target", "Notes"],
      [
        ["API Response Time (p50)", "< 200ms", "For list operations with caching"],
        ["API Response Time (p99)", "< 2000ms", "Worst-case scenarios (large datasets)"],
        ["Cost API Sync Duration", "< 30 seconds", "Update cost records from Azure"],
        ["Resource Sync Duration", "< 120 seconds", "ARM enumeration + DB upsert"],
        ["Optimization Run Duration", "< 5 minutes", "Per 5000 resources"],
        ["Database Query (avg)", "< 100ms", "With proper indexing"],
        ["Frontend Load Time", "< 3 seconds", "First Contentful Paint"],
        ["Auth Token Validation", "< 10ms", "JWT signature verification"]
      ],
      [2000, 1800, 4560]
    ),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== MONITORING & OBSERVABILITY =====
    createHeading("Monitoring & Observability"),

    createHeading("Health Checks", 2),
    createDiagram(`
    ┌─────────────────────────────────────────────┐
    │        Health Check Endpoints               │
    ├─────────────────────────────────────────────┤
    │                                             │
    │  GET /health/live                           │
    │  ├─ Description: Liveness probe             │
    │  ├─ Used by: Kubernetes, App Service       │
    │  ├─ Check: Service is running               │
    │  ├─ Response: {"status": "ok"}              │
    │  └─ Interval: 60 seconds (orchestrator)     │
    │                                             │
    │  GET /health/ready (if implemented)         │
    │  ├─ Description: Readiness probe            │
    │  ├─ Check: Ready to accept traffic          │
    │  │   • Database connectivity                │
    │  │   • Required services accessible         │
    │  └─ Response: Detailed status JSON          │
    │                                             │
    │  GET /api/status                            │
    │  ├─ Description: Detailed system status     │
    │  ├─ Returns:                                │
    │  │   • API version                          │
    │  │   • Database status                      │
    │  │   • Azure connectivity                   │
    │  │   • Last sync timestamp                  │
    │  └─ Accessible: Admin only                  │
    │                                             │
    └─────────────────────────────────────────────┘
    `),

    createHeading("Structured Logging", 2),
    createDiagram(`
    ┌─────────────────────────────────────────────┐
    │      Structured Logging with structlog       │
    ├─────────────────────────────────────────────┤
    │                                             │
    │  Log Streams:                               │
    │                                             │
    │  1. API Request Logging:                    │
    │     {timestamp, method, path, status,       │
    │      response_time_ms, user_id}             │
    │                                             │
    │  2. Database Query Logging:                 │
    │     {timestamp, query_type, table,          │
    │      rows_affected, duration_ms}            │
    │     (Development only, disabled in prod)    │
    │                                             │
    │  3. External API Calls:                     │
    │     {timestamp, api_name, endpoint,         │
    │      status_code, duration_ms, retry_count}│
    │                                             │
    │  4. Error Logging:                          │
    │     {timestamp, level, error_type,          │
    │      message, stack_trace, context}        │
    │                                             │
    │  5. Business Logic Events:                  │
    │     {timestamp, event_type, resource_id,    │
    │      findings_count, total_savings}         │
    │                                             │
    │  Output: JSON format to stdout              │
    │  Collection: App Insights, ELK Stack, etc.  │
    │                                             │
    └─────────────────────────────────────────────┘
    `),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== API OVERVIEW =====
    createHeading("API Endpoints Reference"),

    createHeading("Authentication", 2),
    createTable(
      ["Endpoint", "Method", "Auth", "Purpose"],
      [
        ["POST /api/auth/login", "POST", "None", "Login with credentials, receive JWT token"],
        ["POST /api/auth/logout", "POST", "JWT", "Invalidate current token (optional)"]
      ],
      [2000, 1000, 1200, 4160]
    ),

    createHeading("Cost Management", 2),
    createTable(
      ["Endpoint", "Method", "Auth", "Purpose"],
      [
        ["GET /api/costs/summary", "GET", "JWT", "Cost summary for period (subscription total)"],
        ["GET /api/costs/by-service", "GET", "JWT", "Cost breakdown by Azure service"],
        ["GET /api/costs/by-resource", "GET", "JWT", "Cost by individual resource"],
        ["GET /api/costs/daily", "GET", "JWT", "Daily cost trends (time-series)"],
        ["GET /api/costs/by-resource-group", "GET", "JWT", "Cost aggregated by resource group"]
      ],
      [2000, 1000, 1000, 4360]
    ),

    createHeading("Resource Management", 2),
    createTable(
      ["Endpoint", "Method", "Auth", "Purpose"],
      [
        ["GET /api/resources", "GET", "JWT", "List resources with pagination"],
        ["GET /api/resources/{id}", "GET", "JWT", "Get details of specific resource"],
        ["GET /api/resources/{type}", "GET", "JWT", "List resources by type (VM, Disk, AKS, etc)"],
        ["POST /api/sync", "POST", "JWT+Admin", "Trigger resource inventory sync from Azure"]
      ],
      [2000, 1000, 1200, 4160]
    ),

    createHeading("Optimization & Findings", 2),
    createTable(
      ["Endpoint", "Method", "Auth", "Purpose"],
      [
        ["POST /api/optimize/analyze", "POST", "JWT+Admin", "Execute optimization analysis run"],
        ["GET /api/optimize/findings", "GET", "JWT", "List all optimization findings"],
        ["GET /api/optimize/findings/{id}", "GET", "JWT", "Get finding details with evidence"],
        ["PUT /api/optimize/findings/{id}", "PUT", "JWT+Admin", "Update finding status (remediated/ignored)"],
        ["GET /api/optimize/config", "GET", "JWT+Admin", "Get engine config (enabled rules)"],
        ["PUT /api/optimize/config", "PUT", "JWT+Admin", "Update engine rules & thresholds"]
      ],
      [2000, 1000, 1200, 4160]
    ),

    createHeading("Dashboard & Analytics", 2),
    createTable(
      ["Endpoint", "Method", "Auth", "Purpose"],
      [
        ["GET /api/dashboard", "GET", "JWT", "Dashboard overview (KPIs & summary)"],
        ["GET /api/dashboard/top-spend", "GET", "JWT", "Top spending resources"],
        ["GET /api/dashboard/trends", "GET", "JWT", "Historical cost trends"]
      ],
      [2000, 1000, 1000, 4360]
    ),

    createHeading("Kubernetes Telemetry (Optional)", 2),
    createTable(
      ["Endpoint", "Method", "Auth", "Purpose"],
      [
        ["POST /api/k8s/utilization", "POST", "Token", "Agent submits utilization snapshot"],
        ["GET /api/k8s/utilization", "GET", "JWT", "Query historical utilization data"]
      ],
      [2000, 1000, 1200, 4160]
    ),

    createHeading("System Status", 2),
    createTable(
      ["Endpoint", "Method", "Auth", "Purpose"],
      [
        ["GET /health/live", "GET", "None", "Liveness probe for orchestrators"],
        ["GET /api/status", "GET", "JWT", "Detailed system status"]
      ],
      [2000, 1000, 1000, 4360]
    ),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== DEPLOYMENT CHECKLIST =====
    createHeading("Pre-Deployment Checklist"),

    createHeading("Infrastructure Requirements", 2),
    createText("Before deploying to production:", { bold: true }),
    createText("✓ Azure subscription with sufficient credits and quota", { size: 22 }),
    createText("✓ Resource group created in target Azure region", { size: 22 }),
    createText("✓ PostgreSQL Flexible Server (13+) or compatible database", { size: 22 }),
    createText("✓ App Service plan (Standard tier or higher recommended)", { size: 22 }),
    createText("✓ System-assigned Managed Identity created for App Service", { size: 22 }),
    createText("✓ RBAC roles assigned to Managed Identity:", { size: 22 }),
    createText("  - Cost Management Reader (for Cost API access)", { size: 20 }),
    createText("  - Reader (for Resource Manager enumeration)", { size: 20 }),
    createText("✓ Application Insights created (optional but recommended)", { size: 22 }),
    createText("✓ Key Vault for secrets management (optional but recommended)", { size: 22 }),

    createHeading("Configuration Requirements", 2),
    createText("Environment variables to configure:", { bold: true }),
    createText("✓ DATABASE_URL: PostgreSQL connection string with SSL", { size: 22 }),
    createText("✓ AUTH_ENABLED: Set to 'true' in production", { size: 22 }),
    createText("✓ JWT_SECRET: Strong cryptographic key (32+ characters)", { size: 22 }),
    createText("✓ SETTINGS_ENCRYPTION_KEY: AES-256 key for encrypting sensitive settings", { size: 22 }),
    createText("✓ CORS_ALLOWED_ORIGINS: Frontend URL(s) (comma-separated)", { size: 22 }),
    createText("✓ APP_ENV: Set to 'prod'", { size: 22 }),
    createText("✓ REACT_APP_API_URL: Backend API URL (for frontend)", { size: 22 }),
    createText("✓ K8S_AGENT_TOKEN: Secure token for Kubernetes agent (if deployed)", { size: 22 }),

    createHeading("Post-Deployment Validation", 2),
    createText("After deployment, verify:", { bold: true }),
    createText("✓ Health check endpoint responds: GET /health/live → 200 OK", { size: 22 }),
    createText("✓ Database migrations completed: Alembic upgraded to head", { size: 22 }),
    createText("✓ Initial admin user created", { size: 22 }),
    createText("✓ Frontend loads without CORS errors", { size: 22 }),
    createText("✓ Login works with admin credentials", { size: 22 }),
    createText("✓ Cost API can fetch from Azure (test /api/costs/summary)", { size: 22 }),
    createText("✓ Resource sync completes successfully (POST /api/sync)", { size: 22 }),
    createText("✓ Optimization analysis runs without errors", { size: 22 }),
    createText("✓ Logs are being collected and searchable", { size: 22 }),

    // PAGE BREAK
    new Paragraph({ children: [new PageBreak()] }),

    // ===== CONCLUSION =====
    createHeading("Conclusion"),
    createText("CostOptimizeRecommender is a production-ready enterprise platform built with modern technologies and best practices. The three-tier architecture ensures clear separation of concerns, independent scaling, and robust security. The system integrates seamlessly with Azure Cost Management and Resource Manager while providing a user-friendly interface for cost optimization and resource management."),

    createText("Key strengths of the architecture:"),
    createText("• Scalability: Stateless backend enables horizontal scaling with load balancing", { size: 22 }),
    createText("• Security: JWT authentication, RBAC, Managed Identity, encrypted settings", { size: 22 }),
    createText("• Reliability: Health checks, structured logging, database transactions", { size: 22 }),
    createText("• Observability: Comprehensive logging, metrics, and status endpoints", { size: 22 }),
    createText("• Flexibility: Docker containerization supports App Service, AKS, or on-premises", { size: 22 }),
    createText("• Maintainability: Database migrations, clean code structure, API documentation", { size: 22 }),

    createText("The platform is designed to grow with organizational needs, from small pilots to enterprise-wide deployments managing thousands of resources and millions in cost optimization recommendations."),

    new Paragraph({
      children: [new TextRun("")],
      spacing: { after: 240 }
    }),

    createText("---", { size: 20 }),
    createText("Document Version: 2.0 | Updated: July 2026", { size: 20, italic: true }),
    createText("For questions or updates, refer to the project repository documentation.", { size: 20, italic: true })
  ]
}];

// Create and save document
const doc = new Document({ sections });

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(process.argv[2], buffer);
  console.log(`✓ Document created: ${process.argv[2]}`);
}).catch(err => {
  console.error("Error creating document:", err);
  process.exit(1);
});

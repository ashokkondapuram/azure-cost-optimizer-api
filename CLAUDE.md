# Cost Optimize Recommender - Repository Guide

## Project Overview

**Project:** CostOptimizeRecommender  
**Purpose:** Azure cloud cost optimization analysis and recommendations engine  
**Tech Stack:** Python (FastAPI), React/TypeScript, PostgreSQL, Azure SDK  
**Key Features:** Resource inventory sync, metrics collection, optimization rule engine, cost analysis  

---

## Directory Structure & File Usage

### `/app` - Backend Application Core

#### **Routers & API Endpoints** (`/app/routers/`)
- **`resources_inventory.py`** - Resource listing endpoints
  - Exports: `/resources/{type}` GET endpoints (vms, disks, storage, etc.)
  - Functions: `get_resources_db()`, paginated resource queries
  - Used by: Frontend ResourceList component, cost analysis engine

- **`analysis.py`** - Optimization analysis endpoints
  - Exports: `/analyze`, `/recommendations`, `/optimization-status`
  - Triggers: Metrics fetching, optimization rule execution
  - Used by: Dashboard analysis views, scheduled analysis runs

#### **Resource Definition Layer** (`/app/resources/`)
- **`registry.py`** - Central resource type registry
  - Line 14-29: Imports all resource modules (vm, disk, storage, etc.)
  - Line 73-81: `_build_resource_monitor_profiles()` - Registers metrics
  - Key Function: `get_resource_spec(canonical_type)` - Lookup resource definition
  - Pattern: Each resource module defines `TECHNICAL_FETCH_SPEC` + `MONITOR_PROFILE`

- **`compute/vm.py`** - Virtual Machine resource definition
  - Monitor Metrics: CPU %, Memory %, Network In/Out, Disk I/O
  - Properties Synced: vmSize, powerState, provisioningState, osProfile
  - Threshold Config: `/data/vm_metrics_thresholds.json`

- **`compute/disk.py`** - Managed Disk resource definition
  - Monitor Metrics: Read/Write IOPS, Throughput, Queue Depth, Capacity Used %
  - Properties Synced: diskSizeGB, diskState, diskIOPSReadWrite, diskMBpsReadWrite, managedBy
  - Threshold Config: `it_services/compute_disk/data/managed_disk_metrics_thresholds.json`
  - Used by: Disk optimization analysis (disk_utilization.py)

- **`compute/vmss.py`** - VM Scale Set resource definition
- **`storage/account.py`** - Storage Account resource definition
- **`network/`** - Load Balancer, NSG, NIC, Public IP resources

#### **Metrics Collection & Processing** 
- **`monitor_metrics.py`** (~800 lines) - Azure Monitor API integration
  - Line 335-359: `enrich_derived_monitor_facts()` - Calculates utilization % metrics
  - Line 520-743: `load_azure_monitor_metrics()` - Main fetch orchestrator
  - Uses ThreadPoolExecutor (default 6 workers, max 120s timeout)
  - Error Handling: 404 not found, 403 auth, timeouts tracked separately
  - Used by: metrics_api.py, optimization engines

- **`metrics_api.py`** (~820 lines) - Metrics orchestration layer
  - Line 714: `fetch_metrics_for_subscription()` - Entry point for all metrics fetching
  - Line 470: `fetch_metrics_for_resource()` - Per-resource metric fetch
  - Integration: Calls `get_monitor_profile()` to lookup metric definitions
  - Used by: Analysis engine, optimization rule evaluation

- **`metrics_catalog.py`** - Metric metadata and API shaping
  - Maps Azure Monitor aggregation types to resource metrics
  - Example: `("microsoft.compute/disks", "Composite Disk Read Bytes/sec"): ("Average",)`

- **`metrics_loader.py`** - Database metrics loading and aggregation
  - Loads historical metrics from PostgreSQL metrics table
  - Aggregates metrics across time periods

#### **Disk-Specific Analysis**
- **`disk_utilization.py`** - Disk metrics computation & analysis
  - Line 45-80: `provisioned_iops()`, `provisioned_mbps()` - Extract capacity from disk properties
  - Line 100-120: `peak_disk_iops_utilization_pct()` - Calculates peak IOPS utilization
  - Line 125-140: `disk_iops_utilization_pct()` - Calculates average IOPS utilization
  - Line 160-180: `is_disk_idle_io()` - Checks if I/O below idle threshold
  - Line 200-220: `metrics_block_disk_downgrade()` - Prevents downgrade if utilization is high
  - Used by: `compute/disk/analysis.py` for recommendation rules

- **`managed_disk_catalog.py`** - Disk SKU specifications & thresholds
  - Function: `load_disk_specifications()` - Returns full disk config JSON
  - Function: `optimization_thresholds()` - Returns threshold values
  - Function: `disk_type_spec(sku_name)` - Gets tier info (tier, relative_cost)
  - Data Source: `it_services/compute_disk/data/managed_disk_metrics_thresholds.json`

- **`disk_staleness.py`** - Unattached disk detection
  - Function: `evaluate_unattached_disk()` - Checks age against max_unattached_disk_days

#### **Optimization Engine** (`/app/optimizer/`)
- **`resource_engines/compute/disk/analysis.py`** - Disk-specific recommendations
  - Rule 1: `DISK_UNUSED_EXTENDED` - Unattached disks (>30 days)
  - Rule 2: `DISK_OVERSIZE_EXTENDED` - Premium disks with low I/O (<1024 B/s)
  - Rule 3: `DISK_CAPACITY_RIGHTSIZE_EXTENDED` - Downsizing based on capacity
  - Rule 4: `DISK_QUEUE_DEPTH_EXTENDED` - Queue depth contention detection
  - Rule 5: `DISK_UNDERPROVISIONED` - High IOPS utilization (≥80%)
  - Pattern: Each rule uses `utilization_gate()` check to filter recommendations

- **`resource_engines/compute/disk/optimization_rules.py`** - Disk rule definitions
  - Capacity and queue depth rule implementations
  - Savings calculations for each recommendation type

- **`resource_engines/compute/disk/sub_engine.py`** - Disk sub-engine coordinator
  - Orchestrates all disk optimization rules
  - Called from main analysis pipeline

- **`rule_catalog.py`** - Rule manifest and configuration
  - Maps rule IDs to configurable settings
  - Example: `DISK_OVERSIZE_EXTENDED` uses `disk_io_idle_bps`, `disk_iops_block_downgrade_pct`

#### **Pricing & Cost Analysis**
- **`compute_pricing.py`** - Cost baseline calculations
  - Function: `estimate_disk_capacity_savings()` - 25% factor savings
  - Function: `estimate_disk_monthly_baseline()` - Uses tier relative_cost
  - Integration: Uses `managed_disk_catalog.py` for tier specifications

- **`azure_retail_pricing.py`** - Retail pricing API integration
  - Function: `estimate_disk_tier_savings()` - Premium→Standard downgrade pricing
  - Function: `get_managed_disk_monthly_price()` - Queries Azure Retail Prices API
  - Returns: Detailed pricing breakdown (retail price, actual MTD cost, savings)

#### **Database & Storage** (`/app/data_store/`)
- **`resource_store.py`** - PostgreSQL resource queries
  - Function: `get_resources_db()` - Full resource list with pagination
  - Function: `get_resources_db_page()` - Page-based resource fetching
  - Tables: `ResourceSnapshot`, `metrics_*` (metrics storage by resource type)

- **`subscription_manager.py`** - Azure subscription management
  - Manages subscription credentials and Azure SDK clients

#### **Utility & Support**
- **`azure_monitor_aggregations.py`** - Azure Monitor aggregation mapping
  - Maps each metric to supported aggregation types (Average, Total, Maximum)

- **`metrics_triggers.py`** - Rule registration and metric triggers
  - Registers DISK_UNUSED_EXTENDED, DISK_OVERSIZE_EXTENDED, etc.
  - Connects metrics to rules that consume them

---

### `/data` - Configuration & Specifications

- **`managed_disk_metrics_thresholds.json`** - Disk tier specifications
  - Sections:
    - `disk_types`: Cost multipliers for each tier
    - `disk_tier_specs`: IOPS/throughput baselines by tier and size
    - `downgrade_rules`: When to recommend tier transitions
    - `optimization_thresholds`: IOPS/throughput utilization thresholds
  - Used by: `managed_disk_catalog.py`, optimization rules, metrics computation

- **`vm_metrics_thresholds.json`** - VM optimization thresholds
  - CPU idle %, Memory downsize %, etc.
  - Pattern: Same structure as disk config

- **`load_balancer_metrics_thresholds.json`** - Load Balancer thresholds
- **`storage_account_metrics_thresholds.json`** - Storage optimization thresholds
- **`[service]_metrics_thresholds.json`** - Per-service threshold configs

---

### `/frontend/src` - React UI Layer

#### **Configuration** (`/frontend/src/config/`)
- **`appRegistry.js`** (lines 122-133) - Page registration
  - Registers: `disks`, `vms`, `storage`, `recommendations`, etc.
  - Maps: Route → Component → API Path mapping
  - Example: `{ page_id: "disks", route: "/disks", api: "/resources/disks", component: "ResourceList" }`

- **`azureIconRegistry.js`** - Resource type icon mappings
  - Maps canonical types to Azure icon names
  - Example: `"compute/disk"` → Azure disk icon

- **`assetIcons.js`** - Display name and category mappings
  - Example: `"compute/disk"` → "Managed Disks" (displayed in UI)

#### **Components** (`/frontend/src/components/`)
- **`ResourceList.js`** - Generic resource listing component
  - Props: `resourceType`, `apiPath`, `metrics`
  - Renders: Table with sortable columns, filters, pagination
  - Displays: Resource metrics, costs, optimization status

- **`AnalysisDashboard.js`** - Recommendations dashboard
  - Shows: Optimization opportunities, potential savings
  - Filters: By resource type, severity, savings amount

- **Dashboard Components** - Visualization for metrics and cost trends

---

## Data Flow Architecture

```
Azure Subscription Resources
    ↓
[1] Resource Sync (nightly/on-demand)
    - Calls: Azure Resource Graph API
    - Stores: ResourceSnapshot table
    ↓
[2] Metrics Collection (hourly/on-demand)
    - Calls: Azure Monitor API (parallel workers)
    - Fetches: Last 7 days of metrics (configurable)
    - Stores: metrics_* tables (per resource type)
    - Triggers: enrich_derived_monitor_facts() for computation
    ↓
[3] Optimization Analysis (triggered)
    - Loads: Resource + Metrics from PostgreSQL
    - Evaluates: Optimization rules per resource
    - Computes: Savings estimates via azure_retail_pricing.py
    - Returns: Recommendations list
    ↓
[4] API Response
    - Endpoint: /resources/{type} + /analyze
    - Frontend: ResourceList component displays results
    - UI: Shows metrics, costs, and optimization recommendations
```

---

## Key Patterns & Conventions

### 1. Resource Definition Pattern
Each resource type defines two core objects in `/app/resources/{category}/{type}.py`:

```python
TECHNICAL_FETCH_SPEC = {
    'synced_property_paths': [...],  # Properties to sync from ARM
    'monitor_profile': {...}          # Metrics to collect
}

MONITOR_PROFILE = {
    'arm_type': 'microsoft.compute/disks',
    'metrics': [
        MonitorMetric("Composite Disk Read Bytes/sec", "disk_read_bps", ...),
        ...
    ]
}
```

### 2. Metrics Collection Pattern
1. Define metrics in `MONITOR_PROFILE` (resource module)
2. Register in `registry.py` via `_build_resource_monitor_profiles()`
3. Fetch via `load_azure_monitor_metrics()` (monitor_metrics.py)
4. Enrich via `enrich_derived_monitor_facts()` (compute utilization %)
5. Store in PostgreSQL metrics table

### 3. Optimization Rule Pattern
Each optimization rule:
1. Checks prerequisite thresholds (e.g., `iops_downgrade_max`)
2. Evaluates rule condition (e.g., `if measured_iops < threshold`)
3. Calculates savings via pricing module
4. Blocks if utilization is healthy (e.g., peak IOPS > 50%)
5. Returns recommendation with evidence

Example: `DISK_OVERSIZE_EXTENDED` rule flow:
```
Disk properties → Get baseline IOPS (from disk_tier_specs)
    ↓
Measured metrics → Calculate utilization % (measured / baseline)
    ↓
Check threshold → If utilization < 30% and tier is Premium
    ↓
Block logic → If peak utilization ≥ 50%, skip recommendation
    ↓
Calculate savings → Query azure_retail_pricing.py for target tier cost
    ↓
Return → Recommendation with evidence (current tier, target tier, monthly savings)
```

### 4. Threshold Configuration Pattern
All optimization thresholds live in `/data/{service}_metrics_thresholds.json`:
- **Service metadata**: Documentation links, pricing info
- **Service specs**: Baseline IOPS, throughput per tier/size
- **Optimization thresholds**: Decision points for recommendations
- **Downgrade rules**: When each tier transition is appropriate

---

## Adding New Features

### Adding a New Resource Type
1. Create `/app/resources/{category}/{type}.py`
2. Define `TECHNICAL_FETCH_SPEC` with properties to sync
3. Define `MONITOR_PROFILE` with metrics (if applicable)
4. Add to `ALL_RESOURCE_MODULES` in `registry.py` (line 14-29)
5. Create `/data/{type}_metrics_thresholds.json` for thresholds
6. Add page config in `/frontend/src/config/appRegistry.js`
7. Test via `/resources/{canonical_type}` endpoint

### Adding Metrics to a Resource
1. Add `MonitorMetric(...)` entry to resource's `MONITOR_PROFILE`
2. Update `/data/{service}_metrics_thresholds.json` with new aggregation
3. Add derived metric computation in `enrich_derived_monitor_facts()` (monitor_metrics.py:335)
4. Test metrics fetch via `/analyze` endpoint

### Adding an Optimization Rule
1. Create rule function in `/app/optimizer/resource_engines/{category}/{type}/analysis.py`
2. Register rule in `metrics_triggers.py` with metric dependencies
3. Add configuration to `/data/{service}_metrics_thresholds.json`
4. Implement `estimate_*_savings()` in pricing modules
5. Test via `/analyze` endpoint and verify recommendations appear

### Adding an API Endpoint
1. Create route in `/app/routers/{module}.py`
2. Import necessary models and services
3. Define FastAPI route with proper error handling
4. Return properly serialized response
5. Add OpenAPI documentation via docstring
6. Test with `GET /api/docs` Swagger interface

---

## Critical File References

### Resource Lookup & Registration
- **Resource Registry**: `/app/resources/registry.py:73` - `_build_resource_monitor_profiles()`
- **Get Resource Spec**: `/app/resources/registry.py:150` - `get_resource_spec(canonical_type)`
- **All Resources**: `/app/resources/registry.py:14-29` - Import all resource modules

### Metrics Fetch & Processing
- **Main Metrics Fetch**: `/app/metrics_api.py:714` - `fetch_metrics_for_subscription()`
- **Per-Resource Fetch**: `/app/metrics_api.py:470` - `fetch_metrics_for_resource(resource_id)`
- **Azure Monitor API**: `/app/monitor_metrics.py:520` - `load_azure_monitor_metrics()`
- **Metric Enrichment**: `/app/monitor_metrics.py:335` - `enrich_derived_monitor_facts()`

### Disk-Specific Analysis
- **Disk Utilization**: `/app/disk_utilization.py:100-220` - Utilization calculation functions
- **Disk Thresholds**: `/app/managed_disk_catalog.py` - Threshold loading and access
- **Disk Rules**: `/app/optimizer/resource_engines/compute/disk/analysis.py` - Optimization rules
- **Disk Pricing**: `/app/azure_retail_pricing.py` - Savings calculation

### Database & Storage
- **Resource Queries**: `/app/data_store/resource_store.py` - PostgreSQL queries
- **Metrics Tables**: PostgreSQL `metrics_*` tables (one per resource type)
- **Resource Snapshot**: PostgreSQL `ResourceSnapshot` table (all resources)

### Frontend Integration
- **Route Registration**: `/frontend/src/config/appRegistry.js:122` - Page configuration
- **Resource Display**: `/frontend/src/components/ResourceList.js` - Generic display component
- **API Paths**: Routes use canonical types (e.g., `/resources/compute/disk`)

---

## Configuration & Environment Variables

### Metrics Collection
- `ANALYSIS_MONITOR_METRICS_TIMESPAN` - Default "P7D" (7 days)
- `ANALYSIS_MONITOR_METRICS_LIMIT_PER_TYPE` - Resource limit per type (default unlimited)
- `ANALYSIS_MONITOR_METRICS_TIMEOUT_SEC` - Batch timeout (default 120 seconds)
- `ANALYSIS_MONITOR_METRICS_WORKERS` - Worker threads (default 6, max 8)

### Optimization Thresholds
All thresholds configurable via `/data/{service}_metrics_thresholds.json`:
- **Disk Metrics**: `iops_utilization_medium_pct`, `premium_downgrade_block_iops_pct`, etc.
- **VM Metrics**: `cpu_idle_pct`, `memory_downsize_used_pct_max`, etc.
- **Storage Metrics**: `cool_tier_days_since_access`, `archive_tier_days_since_access`, etc.

---

## Testing & Verification

### Test Metrics Collection
```bash
# Check if metrics are being fetched
curl http://localhost:8000/resources/compute/disk?include_metrics=true

# Verify metrics in response
# Should contain: disk_read_bps, disk_write_bps, disk_read_iops, disk_write_iops, disk_queue_depth, disk_used_pct
```

### Test Optimization Analysis
```bash
# Run analysis to generate recommendations
curl -X POST http://localhost:8000/analyze?resource_type=compute/disk

# Check recommendations
curl http://localhost:8000/recommendations?resource_type=compute/disk
```

### Test Pricing Calculation
```python
# In Python REPL
from app.azure_retail_pricing import estimate_disk_tier_savings
savings = estimate_disk_tier_savings(
    current_tier="Premium_LRS",
    target_tier="StandardSSD_LRS", 
    disk_size_gb=512,
    region="eastus"
)
print(f"Monthly savings: ${savings['monthly_savings_usd']}")
```

---

## Common Tasks & Workflows

### Updating Disk Optimization Thresholds
1. Edit `it_services/compute_disk/data/managed_disk_metrics_thresholds.json`
2. Update `optimization_thresholds` section with new values
3. Restart backend service
4. Test via `/analyze` endpoint to verify recommendations change

### Adding Support for New Disk SKU
1. Edit `it_services/compute_disk/data/managed_disk_metrics_thresholds.json`
2. Add new SKU to `disk_tier_specs` section with size ranges
3. Add downgrade rules if new tier requires different thresholds
4. Test by analyzing disks of that type

### Debugging Missing Metrics
1. Check `MONITOR_PROFILE` exists in resource module
2. Verify resource is in `ALL_RESOURCE_MODULES` in `registry.py`
3. Check Azure Monitor API has data for that metric
4. Verify Azure credentials have "Monitoring Reader" role
5. Check PostgreSQL metrics table has recent data

### Adding Dashboard Widget for New Metric
1. Create new chart component in `/frontend/src/components/`
2. Pass metric data from parent component (e.g., ResourceList)
3. Add configuration to `/frontend/src/config/appRegistry.js` if new page needed
4. Test by loading page and verifying metric displays

---

## Database Schema (Key Tables)

### ResourceSnapshot
```sql
- id: UUID (primary key)
- subscription_id: String
- resource_group: String
- resource_name: String
- resource_type: String (e.g., "Microsoft.Compute/disks")
- canonical_type: String (e.g., "compute/disk")
- arm_id: String (full ARM resource ID)
- properties_json: JSON (synced properties)
- tags_json: JSON (resource tags)
- last_synced: Timestamp
```

### metrics_compute_disk (and similar per resource type)
```sql
- id: UUID
- resource_id: UUID (FK to ResourceSnapshot)
- timestamp: Timestamp
- disk_read_bps: Float
- disk_write_bps: Float
- disk_read_iops: Float
- disk_write_iops: Float
- disk_queue_depth: Float
- disk_used_pct: Float
```

---

## Performance Considerations

- **Metrics Fetch**: Uses 6 parallel workers, 120-second timeout per batch
- **Database Queries**: Indexed on canonical_type, subscription_id, last_synced
- **Frontend Pagination**: Default 50 resources per page, support for cursor-based pagination
- **Azure Monitor API**: Respects rate limits (configurable via WORKERS env var)

---

## Troubleshooting

**Issue: No metrics appear in resource response**
- Check: Azure Monitor API authentication (need Monitoring Reader role)
- Check: Resource has recent activity (metrics require data points)
- Check: MONITOR_PROFILE is registered in registry.py
- Check: PostgreSQL metrics table has recent rows

**Issue: Recommendations missing or incorrect**
- Check: Threshold values in `/data/{service}_metrics_thresholds.json`
- Check: Optimization rule condition logic in analysis.py
- Check: Metrics are being fetched and computed correctly
- Check: Cost/pricing calculation returning expected values

**Issue: API returns 404 for resource type**
- Check: Resource type is in appRegistry.js configuration
- Check: Canonical type matches resource module definition
- Check: Resource module is imported in registry.py

---

## Documentation Links

- **Azure Managed Disks**: https://learn.microsoft.com/en-us/azure/virtual-machines/managed-disks-overview
- **Azure Monitor**: https://learn.microsoft.com/en-us/azure/azure-monitor/
- **Azure Resource Manager**: https://learn.microsoft.com/en-us/azure/azure-resource-manager/
- **FastAPI**: https://fastapi.tiangolo.com/
- **React**: https://react.dev/

---

**Last Updated**: 2026-07-09  
**Repository**: CostOptimizeRecommender  
**Status**: Active Development

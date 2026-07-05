# Metrics and triggers

Generated from `app/metrics_triggers.py`. Do not edit by hand.

| Metric | Direction | Threshold | Cost effect | Performance effect | Rules |
|--------|-----------|-----------|-------------|-------------------|-------|
| `age_days` | high | > snapshot_retention_days (default 90) | Stale snapshots accumulate backup storage cost; deletion recovers full MTD spend. | No workload impact when recovery requirements are validated. | SNAPSHOT_OLD, SNAPSHOT_RETENTION_EXTENDED |
| `api_hits` | both | < kv_api_hits_idle idle · ≥ kv_api_hits_high high-ops | Idle vaults may be deleted; high volume increases per-operation charges. | Low hits indicate no dependency; high hits may need caching not capacity change. | KEYVAULT_IDLE_EXTENDED, KEYVAULT_PREMIUM_EXTENDED, KEYVAULT_HIGH_OPS_EXTENDED |
| `avg_cpu_pct` | both | < 5% idle · < 20% low · > 85% high | Low CPU enables idle VM removal and rightsizing savings (up to 90% MTD). | High CPU blocks downsize; sustained high utilization signals capacity risk. | VM_IDLE, VM_OVERSIZE, VM_UNDERUTILIZED_EXTENDED (+3) |
| `avg_memory_pct` | both | < 30% downsize candidate · > 85% upsize candidate | Low memory supports SKU downgrade and cross-family rightsizing. | High memory blocks downsize and may require upsize. | VM_OVERSIZE, VM_SKU_SIZING_EXTENDED, VM_RIGHTSIZE_FAMILY (+1) |
| `backend_availability_pct` | low | Low backend availability | Removing idle load balancer saves cost only when backends are empty. | Low availability indicates unhealthy backends — fix before removal. | LOAD_BALANCER_IDLE_EXTENDED |
| `byte_count` | low | < 1,000,000 bytes in period | Low traffic on public IPs, NAT gateways, and load balancers may be removable. | Minimal traffic indicates no active workload dependency. | PUBLIC_IP_IDLE_EXTENDED, NAT_GATEWAY_IDLE_EXTENDED, LOAD_BALANCER_IDLE_EXTENDED |
| `cluster_cpu_pct` | low | < 10% per node / cluster | Idle AKS nodes can be scaled down for proportional compute savings. | Very low cluster CPU indicates over-provisioned node pools. | AKS_IDLE_POOL_EXTENDED, AKS_NODE_IDLE |
| `cluster_mem_pct` | low | < 15% per node | Supports idle node pool reduction recommendations. | Low memory headroom may still be required for burst workloads. | AKS_IDLE_POOL_EXTENDED, AKS_NODE_IDLE |
| `cpu_pct` | low | < 10% (SQL serverless candidate) | Low SQL CPU supports serverless or lower tier migration. | Sustained high CPU requires scale-up before cost reduction. | SQL_SERVERLESS_EXTENDED |
| `disk_iops_utilization_pct` | both | < 20% downgrade candidate · ≥ 80% upsize candidate | Low utilization vs provisioned IOPS enables tier downgrade. | Sustained high utilization requires larger disk or higher tier. | DISK_OVERSIZE_EXTENDED, DISK_UNDERPROVISIONED |
| `disk_read_bps` | low | Combined read+write < 1,024 B/s on attached premium disks | Near-zero I/O on premium disks enables tier downgrade savings. | Low I/O confirms disk is not performance-bound. | DISK_UNUSED_EXTENDED, DISK_OVERSIZE_EXTENDED |
| `disk_read_iops` | both | < 20% of cap low · ≥ 80% of cap under-provisioned | Low IOPS utilization supports Premium → Standard SSD downgrade. | High IOPS utilization signals capacity risk; blocks downgrade. | DISK_OVERSIZE_EXTENDED, DISK_UNDERPROVISIONED |
| `disk_write_bps` | low | Combined read+write < 1,024 B/s on attached premium disks | Near-zero I/O on premium disks enables tier downgrade savings. | Low I/O confirms disk is not performance-bound. | DISK_UNUSED_EXTENDED, DISK_OVERSIZE_EXTENDED |
| `disk_write_iops` | both | < 20% of cap low · ≥ 80% of cap under-provisioned | Low IOPS utilization supports Premium → Standard SSD downgrade. | High IOPS utilization signals capacity risk; blocks downgrade. | DISK_OVERSIZE_EXTENDED, DISK_UNDERPROVISIONED |
| `memory_pct` | both | < 35% downsize · blocked if ≥ 80% | Low Redis memory supports smaller cache SKU. | High memory or ops/sec blocks downsize. | REDIS_RIGHTSIZE_EXTENDED |
| `monthly_cost_usd` | high | Drives savings estimates for all cost rules | Higher MTD cost increases absolute savings from optimization actions. | Cost alone does not indicate performance risk. | FIREWALL_FIXED_COST_EXTENDED, CDN_PROFILE_COST_EXTENDED |
| `pull_count` | low | < acr_pull_count_low (default 500) | Low pull volume supports Basic tier ACR instead of Premium. | Low pulls confirm registry is not on a hot deployment path. | ACR_PREMIUM_EXTENDED, ACR_STANDARD_EXTENDED, ACR_STORAGE_HIGH_EXTENDED |
| `push_count` | low | < acr_push_count_low (default 100) | Low push volume with high storage supports image cleanup recommendations. | Low push activity indicates infrequent CI/CD use. | ACR_STORAGE_HIGH_EXTENDED |
| `request_count` | low | < 1,000 requests (AppGW) · < 500 (App Service) | Low request volume supports plan downgrade or resource removal. | Low traffic reduces performance tuning urgency. | APP_GATEWAY_IDLE_EXTENDED, APP_SERVICE_PLAN_EXTENDED |
| `storage_pct` | low | < 40% (PostgreSQL storage) | Low storage utilization supports storage tier reduction. | Monitor growth before reducing provisioned storage. | POSTGRESQL_STORAGE_EXTENDED |
| `storage_used_bytes` | high | >= acr_storage_high_gb (default 50 GB) | High registry storage increases ongoing backup and tier costs. | Storage pressure may slow pulls; cleanup reduces bloat. | ACR_STORAGE_HIGH_EXTENDED, ACR_RETENTION_DISABLED_EXTENDED, ACR_STANDARD_EXTENDED |
| `throttled_search_pct` | high | Elevated throttling indicates capacity pressure | Scaling up search replicas increases cost but may be required. | High throttling degrades query performance — scale or optimize queries. | — |
| `throughput_bytes` | low | < 500 bytes | Idle Application Gateway may be deleted for fixed-cost savings (~40% MTD). | Low throughput confirms gateway is not serving meaningful traffic. | APP_GATEWAY_IDLE_EXTENDED |
| `total_ru` | low | < 50,000 RU | Low RU consumption supports autoscale or manual throughput reduction. | Low RU indicates light workload; watch for latency before reducing. | COSMOS_AUTOSCALE_EXTENDED |
| `transaction_count` | low | < 5,000 transactions | Low transaction volume supports storage lifecycle / tier optimization. | Infrequent access patterns suit cool or archive tiers. | STORAGE_NO_LIFECYCLE, STORAGE_LIFECYCLE_EXTENDED |
| `used_capacity_bytes` | low | Low used capacity vs provisioned (< 25% when capacity known) | Underused storage capacity supports tier and lifecycle policies. | Capacity headroom is healthy unless paired with high transaction load. | STORAGE_NO_LIFECYCLE, STORAGE_LIFECYCLE_EXTENDED |

## Centralized thresholds

| Key | Value |
|-----|-------|
| `acr_pull_count_low` | 500 |
| `acr_push_count_low` | 100 |
| `acr_storage_high_gb` | 50 |
| `api_hits_low` | 10 |
| `byte_count_low` | 1000000 |
| `cpu_high_pct` | 85 |
| `cpu_idle_pct` | 5 |
| `cpu_oversize_pct` | 20 |
| `disk_io_idle_bps` | 1024 |
| `disk_iops_block_downgrade_pct` | 20 |
| `disk_iops_high_util_pct` | 80 |
| `disk_iops_low_util_pct` | 20 |
| `kv_api_hits_high` | 50000 |
| `kv_api_hits_idle` | 10 |
| `memory_high_pct` | 80 |
| `memory_idle_pct` | 30 |
| `packet_count_low` | 100 |
| `pull_count_low` | 500 |
| `request_count_low` | 1000 |
| `rightsizing_block_cpu_pct` | 60 |
| `rightsizing_block_memory_pct` | 80 |
| `snapshot_min_size_gb` | 0 |
| `snapshot_retention_days_default` | 90 |
| `throughput_bytes_low` | 500 |
| `total_ru_low` | 50000 |
| `transaction_count_low` | 5000 |

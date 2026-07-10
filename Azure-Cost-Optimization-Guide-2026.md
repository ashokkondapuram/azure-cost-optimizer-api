# Azure Cost Optimization Reference Guide 2026

Comprehensive cost optimization strategies for 20 Azure resource types with actionable rules, metrics, pricing models, and official documentation.

---

## TABLE OF CONTENTS

1. [Database & Data Services](#database--data-services)
   - Azure SQL Database / SQL Server
   - MySQL / MariaDB
   - Azure Synapse Analytics
   - Azure Data Factory
   - Azure Stream Analytics
   - Azure Cognitive Search

2. [Integration & Messaging](#integration--messaging)
   - Event Hubs
   - Service Bus
   - API Management
   - Logic Apps

3. [Monitoring & Logging](#monitoring--logging)
   - Application Insights
   - Log Analytics / Monitor
   - Azure Backup

4. [Security & Identity](#security--identity)
   - Key Vault
   - Azure Sentinel

5. [Analytics](#analytics)
   - Power BI
   - Azure Data Explorer

6. [Networking - Additional](#networking---additional)
   - VPN Gateway
   - ExpressRoute
   - CDN / Front Door / Traffic Manager

---

# DATABASE & DATA SERVICES

## 1. Azure SQL Database / SQL Server

### Pricing Model
- **Compute Pricing**: vCore-based or DTU-based purchasing models
  - vCore: General Purpose (GP), Business Critical (BC), Hyperscale (HS) tiers
  - DTU: Basic (B), Standard (S), Premium (P) tiers
- **Billing**: Hourly compute charges + storage (per GB/month) + backup storage (LTR charges)
- **Purchase Options**:
  - Pay-as-you-go: Full hourly rates
  - Azure Reservations: 33% discount (1-year) or higher (3-year)
  - Savings Plans for Databases: Up to 35% savings with flexible hourly commitment
  - Azure Hybrid Benefit: Up to 55% savings for existing SQL Server licenses
- **Regional Pricing**: Varies by region; US East typically baseline
- **Serverless Compute**: Per-minute billing, automatic pause/resume during inactivity

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| CPU Percentage | > 80% | Critical |
| Data IO Percentage | > 85% | Critical |
| Log IO Percentage | > 85% | Critical |
| Storage Used | > 85% of max | Warning |
| DTU/vCore Utilization | > 75% sustained | Evaluate scaling |
| Active Connections | Trending upward | Monitor for bottlenecks |
| Query Wait Time | > 1000ms p99 | Performance issue |
| Lock Waits | > 100ms average | Query optimization needed |
| Memory Percentage | > 90% | Critical |
| Session Count | > Max - 20 buffer | Near capacity |

### Cost Optimization Rules (with Savings %)
1. **Use Elastic Pools for Variable Workloads**: Consolidate multiple databases with unpredictable usage patterns. **Savings: 30-40%** vs. provisioning same vCore count separately
2. **Right-Size Compute Tier**: Start with lower tier (Standard/GP) if workload allows, upgrade only when sustained > 80% utilization. **Savings: 25-35%** by avoiding Premium/BC tier overprovisioning
3. **Implement Serverless Compute**: For dev/test/intermittent workloads, use serverless auto-pause (30 min idle). **Savings: 40-60%** during non-business hours
4. **Optimize Storage**: Remove unused indexes, implement data compression, set appropriate backup retention (LTR). **Savings: 15-25%** on storage costs
5. **Use Reserved Instances + Hybrid Benefit**: Combine 3-year reservations (33% off) with SQL Server licensing. **Savings: 45-55%** for committed workloads

### Documentation URLs
- [Azure SQL Database Cost Management](https://learn.microsoft.com/en-us/azure/azure-sql/database/cost-management)
- [Azure SQL Database Pricing](https://azure.microsoft.com/en-us/pricing/details/azure-sql-database/single/)
- [vCore vs DTU Purchasing Models](https://learn.microsoft.com/en-us/azure/azure-sql/database/service-tiers-sql-database-vcore)
- [Elastic Pools Overview](https://learn.microsoft.com/en-us/azure/azure-sql/database/elastic-pool-overview)

---

## 2. Azure Database for MySQL / MariaDB

### Pricing Model
- **Compute Pricing**: Per vCore-hour (Flexible Server)
  - Burstable tier: Lower baseline hourly rate with CPU bursting
  - General Purpose tier: Standard pricing for steady workloads
  - Memory Optimized tier: Premium pricing for in-memory optimization
- **Storage**: Per GB/month, includes free backup storage up to 100% of provisioned size
- **Automatic IOPS Scaling**: Pay only for IOPS actually used (no idle charge)
- **Purchase Options**:
  - Pay-as-you-go: Full rates
  - Reserved Instances: Save 48% with 1-year or 3-year commitment
- **Flexible Server Benefits**: Stop/start capability (no charges when stopped), better cost control
- **Regional Pricing**: Varies; consider multi-region deployment costs

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| CPU Percentage | > 75% sustained | Evaluate scaling |
| Memory Percentage | > 85% | Near capacity |
| Storage Used | > 85% max | Warning |
| I/O Operations Percentage | > 80% | Performance impact |
| Active Connections | > 80% of max | Capacity limit approaching |
| Replication Lag | > 5 seconds | Sync issue |
| Network In/Out | Baseline trending up | Monitor for DDoS |
| Disk Read/Write Latency | > 100ms p99 | Performance degradation |
| Query Count (slow queries) | > 10% of total | Optimization needed |
| Backup Storage Used | Growing rapidly | Review retention policy |

### Cost Optimization Rules (with Savings %)
1. **Use Burstable Tier for Dev/Test**: Development servers rarely need full sustained compute. **Savings: 40-50%** vs. General Purpose
2. **Reserved Instances (1-year minimum)**: Commit to baseline capacity for predictable workloads. **Savings: 30%** on compute
3. **Combine with 3-Year Commitment**: For stable production. **Savings: 48%** vs. pay-as-you-go
4. **Disable Auto-Backup if Non-Critical**: Backup storage beyond 100% has cost. Set appropriate retention. **Savings: 10-20%** on storage
5. **Stop Dev Databases After Hours**: Flexible Server allows pause/resume. **Savings: 50-60%** for after-hours dev environments

### Documentation URLs
- [MySQL Cost Optimization Best Practices](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-db-mysql-cost-optimization)
- [MySQL Pricing - Flexible Server](https://azure.microsoft.com/en-us/pricing/details/mysql/)
- [Reserved Capacity Pricing](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concept-reserved-pricing)
- [Service Tiers - Burstable vs General Purpose](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-service-tiers-storage)

---

## 3. Azure Synapse Analytics

### Pricing Model
- **Dedicated SQL Pool**: DWU-based (Data Warehouse Units)
  - Billed per DWU-hour (minimum 100 DWU)
  - Charges continue even during idle periods
  - Auto-pause feature available to reduce idle costs
- **Serverless SQL Pool**: Per TB of data processed
  - Only charged for data scanned, not compute resources
  - More cost-effective for irregular, ad-hoc queries
- **Spark Pool**: Per vCore-hour, billed for compute + auto-provisioned 
  - Time-to-Live (TTL) keeps cluster warm but continues billing
- **Pre-Purchase Plans (SCU)**: 100,000 SCUs for ~$82,000 = 18% discount off retail
- **Storage**: Separate charge for Data Lake Gen2 (also charged independently)

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Active Queries | > 20 concurrent | Bottleneck risk |
| DWU Utilization | > 80% sustained | Scale up needed |
| Query Execution Time | > 5 min p99 | Investigate long-running |
| CPU Percentage | > 85% | Near capacity |
| Memory Utilization | > 90% | Critical |
| Tempdb Usage | > 50% available | Monitor spill to disk |
| Data Processed (Serverless) | Trending rapidly | Unexpected cost spike |
| Spark Job Duration | > SLA baseline | Cluster sizing review |
| Storage Growth Rate | Accelerating | Partition/cleanup review |
| Pause/Resume Events | Frequency increasing | Potential waste |

### Cost Optimization Rules (with Savings %)
1. **Enable Auto-Pause for Dedicated SQL Pool**: Set 5-15 min idle timeout. **Savings: 40-60%** for dev/test environments
2. **Use Serverless SQL Pool for Ad-Hoc Queries**: Replaces DWU for one-off analytics. **Savings: 60-80%** vs. maintaining dedicated pool for irregular queries
3. **Right-Size DWU Allocation**: Start at DWU100, scale up only when sustained > 80%. **Savings: 20-30%** by avoiding oversizing
4. **Pre-Purchase SCUs for Committed Workloads**: Annual contracts get 18% discount. **Savings: 18%** on all applicable services
5. **Partition Large Tables & Use Appropriate Formats**: Parquet compression + partitioning. **Savings: 30-40%** on storage and query cost

### Documentation URLs
- [Plan & Manage Costs - Synapse Analytics](https://learn.microsoft.com/en-us/azure/synapse-analytics/plan-manage-costs)
- [Synapse Pricing Details](https://azure.microsoft.com/en-us/pricing/details/synapse-analytics/)
- [Dedicated SQL Pool Performance Tuning](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/pause-and-resume-compute-portal)
- [Serverless SQL Pool Cost Management](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql/data-processed)

---

## 4. Azure Data Factory

### Pricing Model
- **Orchestration Activity Runs**: Per million activity executions
  - Web activities, copy activities, custom activities all count
  - First 50,000 runs/month free tier
- **Data Integration Unit (DIU) Hours**: For copy activities on Azure IR
  - Billed for DIU-hours; scale from 2-256 DIUs as needed
  - Less expensive for high-throughput; more expensive for small operations
- **Data Flow vCore-Hours**: For mapping data flows
  - Charged for compute type, vCore count, execution duration
  - Includes cluster startup time + TTL keep-alive
- **Self-Hosted Integration Runtime**: Free; runs on your infrastructure
- **Reserved Instances**: Available for data flows (1 or 3-year discounts)

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Activity Run Duration | Baseline variance | Investigate delays |
| DIU Utilization | > 75% average | Optimize or resize |
| Data Movement Volume | Trending up | Monitor egress costs |
| Pipeline Success Rate | < 95% | Review failures |
| Trigger Latency | > SLA | Performance issue |
| Copy Activity Throughput | Below expected MB/s | Configuration review |
| Data Flow Compute Time | Increasing trend | Optimize transformations |
| TTL Keep-Alive Duration | Excessive | Tune timeout value |
| Self-Hosted IR Availability | < 99.9% | Redundancy needed |
| Failed Activity Runs | > 1% of total | Error pattern analysis |

### Cost Optimization Rules (with Savings %)
1. **Use Self-Hosted IR for Frequent Operations**: Eliminates DIU charges for on-premises/hybrid transfers. **Savings: 40-60%** for high-volume data movement
2. **Optimize DIU Allocation**: Start low (2 DIU), increase only if throughput insufficient. **Savings: 30-40%** by right-sizing
3. **Avoid Unnecessary Mapping Data Flows**: Use copy activity + data transformation elsewhere when possible. **Savings: 50-70%** for simple transformations
4. **Enable Data Flow Caching & Debug Mode Sparingly**: Cache is charged per execution; debug mode uses vCore-hours. **Savings: 20-30%** by limiting dev iterations
5. **Batch Small Operations into Single Runs**: Combine multiple small copy activities into one. **Savings: 15-25%** by reducing activity count

### Documentation URLs
- [Plan & Manage Costs - Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/plan-manage-costs)
- [Data Pipeline Pricing](https://azure.microsoft.com/en-us/pricing/details/data-factory/data-pipeline/)
- [Understanding Pricing Through Examples](https://learn.microsoft.com/en-us/azure/data-factory/pricing-concepts)
- [Applying FinOps to Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/apply-finops)

---

## 5. Azure Stream Analytics

### Pricing Model
- **Streaming Unit (SU) v2 Model** (default):
  - Pay per SU per month; 1 SU = $240.90/month (50% reduction vs. v1)
  - Tiered pricing: Higher volume = lower per-SU rate
  - Auto-scale SUs based on demand (scales 1-384 SUs)
- **V1 Model** (legacy, still available):
  - $0.11/hour per SU; higher cost than v2
- **Regional Pricing Variation**: Some regions have different rates
- **No Upfront Costs**: Pay-as-you-go; stop job to stop charges
- **Free Tier**: First 4 SU-months free per month

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| SU Utilization | > 80% sustained | Scale up needed |
| Input Events/Sec | Baseline trending up | Capacity planning |
| Output Events/Sec | Below expected | Query issue |
| Backlog Events | > 0 | Input queue filling |
| Runtime Errors | > 0.1% | Investigation needed |
| Watermark Delay | > SLA (seconds) | Query optimization |
| Query Complexity | Increasing | Simplification review |
| Partitions Used | Approaching max | Repartition strategy |
| Late Arrival Duration | Trending up | Window tuning |
| Deserialization Errors | Any detected | Data format issue |

### Cost Optimization Rules (with Savings %)
1. **Use Streaming Unit v2 Model**: 50% cheaper than legacy v1 ($240/month vs. $800+ for equivalent v1 capacity). **Savings: 50%** automatic from v1 migration
2. **Right-Size SU Allocation**: Start with 1 SU; scale only when > 80% utilization. **Savings: 40-50%** by avoiding overprovisioning
3. **Optimize Query Complexity**: Simpler queries = fewer SU requirements. **Savings: 20-30%** through query tuning
4. **Use Auto-Scale for Variable Workloads**: Automatically adjust SUs between min/max based on metrics. **Savings: 30-40%** during low-traffic periods
5. **Filter Early in Pipeline**: Remove unnecessary data before transformation stages. **Savings: 15-25%** by reducing data processed

### Documentation URLs
- [Stream Analytics Pricing](https://azure.microsoft.com/en-us/pricing/details/stream-analytics/)
- [New Competitive Pricing Model](https://techcommunity.microsoft.com/blog/analyticsonazure/azure-stream-analytics-has-launched-a-new-competitive-pricing-model/3827693)
- [Stream Processing Architecture Reference](https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/data/stream-processing-stream-analytics)

---

## 6. Azure Cognitive Search (AI Search)

### Pricing Model
- **Dedicated Model** (default):
  - Search Units (SUs) with hourly charges
  - Per SU pricing varies by tier (Free, Basic, S1-S3, L1-L2)
  - Fixed hourly billing regardless of usage
  - Best for steady, predictable workloads
- **Serverless Model** (Preview):
  - Consumption-based: Compute Units per hour (CU/hr) + per-GB storage
  - Auto-scales from zero; ideal for bursty/variable workloads
  - Lower cost for intermittent usage
- **Premium Features**: Semantic ranker, AI enrichment, vector search all incur additional charges
- **Storage**: Separate charges for indexed data (per GB/month)
- **Regional Pricing**: Varies by region

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Queries Per Second (QPS) | Baseline trending | Capacity planning |
| Search Latency | > 500ms p99 | Investigate bottleneck |
| Indexing Throughput | Below target docs/sec | Index performance |
| Storage Used | > 85% available | Cleanup/archive needed |
| SU Utilization | > 75% sustained | Scale up |
| Failed Queries | > 0.1% | Query validation |
| Semantic Ranker Usage | Trending up | Cost monitoring |
| AI Enrichment Operations | Growing rapidly | Unexpected charges |
| Index Count | Proliferation detected | Consolidation opportunity |
| Partition Count | Increasing linearly | Query pattern review |

### Cost Optimization Rules (with Savings %)
1. **Use Serverless for Development/Testing**: Completely free during idle periods; no minimum cost. **Savings: 70-90%** vs. dedicated tier for dev
2. **Consolidate Indexes**: Multiple small indexes = redundant overhead. **Savings: 25-40%** by merging semantic duplicates
3. **Implement Incremental Indexing**: Process only new/changed data vs. full reindex. **Savings: 30-50%** on indexing operations
4. **Cache Enriched Content & Use Knowledge Store**: Avoid re-enriching same data. **Savings: 40-60%** on AI enrichment
5. **Right-Size Replicas/Partitions**: Start with 1 replica, 1 partition; scale only when needed. **Savings: 20-35%** by avoiding overprovisioning

### Documentation URLs
- [Plan & Manage Costs - Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-sku-manage-costs)
- [Pricing - Azure AI Search](https://azure.microsoft.com/en-us/pricing/details/search/)
- [Service Tier Selection & Capacity Planning](https://learn.microsoft.com/en-us/azure/search/search-sku-tier)
- [Estimate Capacity for Query and Index Workloads](https://learn.microsoft.com/en-us/azure/search/search-capacity-planning)

---

# INTEGRATION & MESSAGING

## 7. Azure Event Hubs

### Pricing Model
- **Throughput Units (TUs)** - Standard Tier:
  - Hourly billing per TU (minimum 1 TU)
  - 1 TU = 1 MB/sec ingress, 2 MB/sec egress
  - Auto-inflate available (scales up automatically)
- **Processing Units (PUs)** - Premium Tier:
  - Higher throughput; billed hourly per PU
  - Includes Capture feature, geo-disaster recovery
- **Capacity Units (CUs)** - Dedicated Tier:
  - Exclusive capacity; highest performance
  - Monthly commitment model
- **Ingress Events**: Pay per million events (Standard/Basic)
- **Regional Pricing**: Varies by geography

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Throughput Unit Usage | > 80% sustained | Auto-scale up |
| Incoming Messages/Sec | Baseline trending | Capacity planning |
| Outgoing Messages/Sec | Below expected | Consumer lag |
| Connection Count | > 80% of limit | Active connections review |
| User Errors | Any detected | Configuration issue |
| Server Errors | Any detected | Investigate immediately |
| Throttled Requests | Any detected | Exceeding capacity |
| Namespace Message Count | > 80% max | Partition/retention review |
| Captured Data Size | Growing rapidly | Retention policy check |
| Partition Count | At maximum | Consider scaling |

### Cost Optimization Rules (with Savings %)
1. **Use Basic Tier for Development**: No Capture, no geo-recovery needed for dev. **Savings: 50%** vs. Standard tier
2. **Disable Auto-Inflate by Default**: Manually scale instead to control costs. **Savings: 20-30%** by preventing unplanned scaling
3. **Set Appropriate Message Retention**: Default 1 day is often sufficient; longer retention = more storage. **Savings: 10-20%** per day reduction
4. **Consolidate Partitions**: Only scale to needed partitions; extra partitions = extra cost. **Savings: 15-25%** through right-sizing
5. **Use Standard Tier with Manual Scaling**: For predictable workloads, avoid Premium unless geo-redundancy required. **Savings: 25-35%** vs. Premium

### Documentation URLs
- [Event Hubs Pricing](https://azure.microsoft.com/en-us/pricing/details/event-hubs/)
- [Compare Event Hubs Tiers](https://learn.microsoft.com/en-us/azure/event-hubs/compare-tiers)
- [Event Hubs Quotas and Limits](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-quotas)
- [Scalability Guide](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-scalability)

---

## 8. Azure Service Bus

### Pricing Model
- **Basic Tier**:
  - Lowest cost; no transactions or PUs
  - Per million operations (send, receive, peek, etc.)
  - No queues/topics count limit
- **Standard Tier**:
  - Higher throughput; per-million-operations billing
  - Slightly higher per-operation cost than Basic
  - Supports more features
- **Premium Tier**:
  - Messaging Units (MUs) - hourly charges
  - Dedicated capacity; resource isolation
  - Fixed monthly cost regardless of operations
  - Best for predictable, high-volume workloads
- **Regional Pricing**: Standard pricing varies by region

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| CPU Usage | > 75% (Premium) | Scale up units |
| Memory Usage | > 85% | Potential bottleneck |
| Active Connections | > 80% of limit | Connection pool review |
| Message Count | Growing steadily | Retention/purge strategy |
| Operation Count | Spiking | Investigate cause |
| Dead-Letter Queue Count | Growing | Message processing issue |
| Forward/Clone Activity | Trending up | Cost multiplication point |
| User Errors | Growing | API usage issue |
| Server Errors | Any rate | Investigation needed |
| Receive Loop Frequency | > expected | Inefficient polling |

### Cost Optimization Rules (with Savings %)
1. **Use Receive Loop with Long-Polling vs. Tight Loop**: Reduces receive operations 10-100x. **Savings: 40-60%** through long-polling (20-30 sec timeout)
2. **Premium Tier Only for > 5M Operations/Month**: Fixed MU cost breaks even above this threshold. **Savings: 30-50%** by using Standard until volume justifies Premium
3. **Implement Batching**: Send/receive multiple messages per operation. **Savings: 50-80%** with message batching
4. **Set Appropriate TTL (Time-To-Live)**: Remove stale messages; reduces storage. **Savings: 10-15%** per day through shorter TTL
5. **Monitor CPU < 20% on Premium**: Right-size MUs to actual usage. **Savings: 25-40%** by scaling down overprovisioned units

### Documentation URLs
- [Service Bus Pricing](https://azure.microsoft.com/en-us/pricing/details/service-bus/)
- [Architecture Best Practices - Service Bus](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-service-bus)
- [Billing & Metrics](https://techcommunity.microsoft.com/t5/messaging-on-azure/azure-service-bus-billing-vs-metrics-vs-current-monthly-cost/ba-p/370861)
- [Quotas and Limits](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-quotas)

---

## 9. Azure API Management

### Pricing Model
- **Consumption SKU**:
  - Pay-per-request model
  - No base fee; billed per API call
  - Best for variable/low-volume traffic
- **Developer SKU**:
  - No SLA; dev/test only
  - Single unit; low fixed cost
  - Not suitable for production
- **Standard SKU**:
  - Fixed hourly cost per unit
  - Includes redundancy; scalable
  - Best for predictable, moderate traffic
- **Premium SKU**:
  - Highest cost; multi-region support
  - Required for advanced features (zones, workspaces)
  - Monthly per-unit pricing
- **Workspaces** (multi-tenancy within instance): No additional charge but operational overhead

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| CPU Utilization | > 80% sustained | Scale out |
| Memory Usage | > 85% | Near capacity |
| Request Count | Trending up | Capacity planning |
| Throttled Requests | Any rate | Exceeding capacity |
| Backend Latency | > baseline | Backend issue |
| Gateway Latency | > SLA | Policy/config review |
| Failed Requests | > 0.5% | Error rate spike |
| Network Bandwidth | Spiking | Egress cost driver |
| API Call Volume | Baseline variance | Traffic pattern change |
| Cache Hit Ratio | < 60% | Cache policy review |

### Cost Optimization Rules (with Savings %)
1. **Consumption Tier for Variable/Unpredictable Traffic**: No base fee; pay only for calls made. **Savings: 50-80%** for APIs with < 1M calls/month
2. **Standard Tier for Stable > 1M Calls/Month**: Fixed cost becomes more economical. **Savings: 40-60%** at high volumes
3. **Avoid Premium for Single-Region**: Premium required only for multi-region. **Savings: 50%** by staying Standard if single-region
4. **Implement Caching Policies**: Cache responses to reduce backend calls. **Savings: 30-50%** through reduced origin traffic
5. **Use Rate-Limiting & Quotas**: Prevent abuse and limit billable operations. **Savings: 20-40%** by controlling request spike abuse

### Documentation URLs
- [Plan & Manage Costs - API Management](https://learn.microsoft.com/en-us/azure/api-management/plan-manage-costs)
- [API Management Pricing](https://azure.microsoft.com/en-us/pricing/details/api-management/)
- [Architecture Best Practices - Cost Optimization](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/api-management/cost-optimization)
- [Feature Comparison by Tier](https://learn.microsoft.com/en-us/azure/api-management/api-management-features)

---

## 10. Azure Logic Apps

### Pricing Model
- **Consumption Plan** (multitenant):
  - Pay-per-execution model
  - No base fee
  - Trigger-based (each trigger run = billable unit)
  - Built-in actions cheaper than connectors
- **Standard Plan** (single-tenant):
  - Hourly pricing per plan instance
  - Fixed cost; flat monthly rate
  - Better for predictable, high-volume workflows
- **Integration Service Environment (ISE)**:
  - Premium option; dedicated infrastructure
  - Monthly commitment model
- **Connector Types**:
  - Built-in triggers/actions: Cheap/free per execution
  - Standard connectors: $0.10-$2.00 per execution
  - Premium connectors: Higher per-execution cost

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Trigger Runs | Trending significantly | Cost projection |
| Action Executions | Rapidly increasing | Unexpected volume |
| Run Duration | > SLA baseline | Performance issue |
| Error Rate | > 1% | Quality issue |
| Connector Usage | By type tracked | Cost breakdown |
| Storage Consumption | Growing | State/history size |
| Integration Account Usage | Approaching limit | Capacity review |
| Trigger Latency | > acceptable | Responsiveness issue |
| Concurrent Runs | Approaching limit | Throttling risk |
| Retry Attempts | Increasing | Upstream issue |

### Cost Optimization Rules (with Savings %)
1. **Consumption Plan for < 10K Runs/Month**: Per-execution cheap for low volume. **Savings: 70-90%** vs. Standard
2. **Standard Plan for > 10K Runs/Month**: Fixed cost becomes economical. **Savings: 40-60%** for high-volume workflows
3. **Use Built-In Actions vs. Connectors**: Built-ins are 50-90% cheaper per execution. **Savings: 50-80%** by minimizing premium connector use
4. **Disable Logic App When Not Needed**: Reduces unnecessary trigger evaluations. **Savings: 20-30%** by using schedules
5. **Batch Processing**: Process multiple items in single trigger instead of per-item triggers. **Savings: 50-70%** through batching strategy

### Documentation URLs
- [Plan & Manage Costs - Logic Apps](https://learn.microsoft.com/en-us/azure/logic-apps/plan-manage-costs)
- [Logic Apps Pricing](https://azure.microsoft.com/en-us/pricing/details/logic-apps/)
- [Usage Metering & Pricing](https://learn.microsoft.com/en-us/azure/logic-apps/logic-apps-pricing)
- [Standard Workflows Vs. Consumption](https://learn.microsoft.com/en-us/azure/logic-apps/single-tenant-overview-compare)

---

# MONITORING & LOGGING

## 11. Application Insights

### Pricing Model
- **Ingestion Charges** (primary cost):
  - Per GB of data ingested
  - Free: 5 GB/month
  - Additional: Variable per-GB rate (decreases with higher volume)
  - OpenTelemetry SDK pre-aggregates metrics (reduces volume)
- **Retention**:
  - First 90 days: Included in ingestion rate
  - Beyond 90 days: Separate long-term retention charge
- **Premium Features**:
  - Workspace-based AI: Access to commitment tiers
  - Basic Logs tier: Lower ingestion rate for infrequent queries
- **Workspace-Based Deployment**: Preferred; enables commitment tiers & cost optimizations
- **Regional Pricing**: Varies by geography

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Daily Ingestion Volume | > 10GB/day | High ingestion alert |
| Ingestion Rate Trend | +20% MoM | Investigate spike |
| Sampling Rate | < 50% coverage | Losing granularity |
| Custom Metric Volume | Rapidly growing | High-cardinality check |
| Exception Rate | > baseline | Application issue |
| Page Load Time | > SLA | Performance degradation |
| Dependency Call Duration | > baseline | Backend latency |
| Failed Requests | > 0.5% | Error rate spike |
| AJAX Call Volume | Spiking | Potential abuse |
| Availability Test Results | < 99% success | Synthetic monitoring alert |

### Cost Optimization Rules (with Savings %)
1. **Use Workspace-Based AI**: Enables commitment tiers (100GB/day = 30% discount). **Savings: 20-40%** through consolidation
2. **Implement Sampling**: 10-50% sampling based on volume; statistical analysis still valid. **Savings: 50-90%** through sampling
3. **Disable Ajax Call Collection**: Often not needed; optional in SDK config. **Savings: 10-15%** by disabling collection
4. **Filter at SDK Level**: Use processors/middleware to exclude telemetry early. **Savings: 20-50%** through pre-filtering
5. **Use OpenTelemetry Pre-Aggregated Metrics**: Reduces custom metrics volume by 80%. **Savings: 40-70%** for high-cardinality dimensions

### Documentation URLs
- [Azure Monitor Cost & Usage](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/cost-usage)
- [Pricing - Azure Monitor](https://azure.microsoft.com/en-us/pricing/details/monitor/)
- [Architecture Best Practices - Application Insights](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/application-insights/cost-optimization)
- [Cost Optimization Best Practices](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/best-practices-cost)

---

## 12. Log Analytics / Azure Monitor

### Pricing Model
- **Data Ingestion** (primary cost):
  - Analytics Logs: Full analytics with all features; per-GB ingestion charge
  - Basic Logs: Low-cost alternative; reduced query capabilities
  - Auxiliary Logs: Minimal features; lowest cost
- **Commitment Tiers** (volume discounts):
  - 100 GB/day → 200 GB/day → 500 GB/day → 1 TB/day → 5 TB/day
  - Commitment tier provides 20-30% discount vs. pay-as-you-go
- **Data Retention**:
  - Default: 31 days (included)
  - Extended retention: Per-GB/month extra charge
  - Long-term retention: Archive to storage (much cheaper)
- **Dedicated Clusters**:
  - 100 GB/day minimum commitment
  - Shares commitment tier across multiple workspaces
  - Good for organizations with > 500GB/day aggregate

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Daily Ingestion Volume | Growing trend | Cost projection |
| Table-by-Table Ingestion | Top tables identified | Optimization target |
| Data Retention Cost | % of total | Evaluate archive |
| Query Costs | Baseline variance | Expensive queries |
| Log Count Anomaly | +20% vs baseline | Investigate spike |
| VM Agent Retention | Excessive log volume | Agent config review |
| Duplicate Data Ingestion | Detected | Workspace consolidation |
| Search Job Costs | Growing rapidly | Archive older data |
| Commit Tier Utilization | 80-100% consistent | Right-sized |
| Ingestion Lag | > SLA | Performance issue |

### Cost Optimization Rules (with Savings %)
1. **Use Commitment Tiers for > 100GB/day**: 20-30% discount vs. pay-as-you-go. **Savings: 20-30%** through commitment
2. **Configure Basic Logs for Infrequent Tables**: Debugging/audit tables; query-charge offset savings. **Savings: 50-70%** on ingestion
3. **Set Data Retention to 31 Days or Less**: Unless compliance requires longer; each extra day = cost. **Savings: 5-10%** per day
4. **Implement Long-Term Retention**: Archive to storage after 90 days; query via search jobs. **Savings: 80-90%** for cold data
5. **Consolidate Workspaces into Dedicated Cluster**: Share commitment tier across 10+ workspaces. **Savings: 25-35%** through consolidation

### Documentation URLs
- [Log Analytics Cost Calculations & Options](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/cost-logs)
- [Cost Optimization in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/best-practices-cost)
- [Change Pricing Tier for Workspace](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/change-pricing-tier)
- [Analyze Workspace Usage](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/analyze-usage)

---

## 13. Azure Backup

### Pricing Model
- **Protected Instance (Per-VM/Server)**: Monthly charge per backed-up resource
  - On-premises servers: $15-20/month per server
  - Azure VMs: $5-10/month per VM (region-dependent)
- **Backup Storage**: Charged per GB stored (compressed)
  - GRS (geo-redundant): Standard cost
  - LRS (locally redundant): ~15% cheaper
  - RAGRS (for cross-region restore): Premium cost
- **Backup Operations**:
  - Daily/weekly/monthly/yearly snapshots (separate costs)
  - Retention period directly impacts cost
- **Reserved Capacity Discounts**:
  - 100 TB → 1 PB annual commitment: 15-20% discount
- **Selective Disk Backup**: Only back up needed disks to reduce size

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Protected Instance Count | Growing | Evaluate necessity |
| Backup Storage Used | Trending up | Retention policy review |
| Backup Job Duration | Exceeding SLA | Performance issue |
| Daily Churn Rate | > 5% | High-change data |
| Restore Success Rate | < 99% | Backup quality issue |
| Retention Point Count | Exponential growth | Retention policy issue |
| Snapshot Storage | Rapid growth | Review snapshot policy |
| Cross-Region Restore Usage | Frequency increasing | Cost multiplier |
| Deleted Item Recovery | Growing backlog | Cleanup needed |
| Compliance Hold Status | Unexpectedly long | Policy review |

### Cost Optimization Rules (with Savings %)
1. **Use Daily Differential + Weekly/Monthly Full Backups**: Reduces stored data vs. daily full. **Savings: 40-50%** vs. all daily full backups
2. **Reduce Instant Restore Snapshots**: Default 5 days; reduce to 2 days if acceptable. **Savings: 20-25%** on snapshot storage
3. **Implement Selective Disk Backup**: Exclude non-essential disks (e.g., temp storage). **Savings: 30-50%** by backing up OS disk only
4. **Use LRS Backup Storage for Non-Critical**: GRS not needed for all workloads. **Savings: 15%** using LRS instead of GRS
5. **Shorten Retention for Dev/Test**: Daily backups → 7 days; no weekly/monthly. **Savings: 60-80%** for dev environment

### Documentation URLs
- [Azure Backup Pricing](https://azure.microsoft.com/en-us/pricing/details/backup/)
- [Azure Backup Pricing Deep Dive](https://learn.microsoft.com/en-us/azure/backup/azure-backup-pricing)
- [5 Ways to Optimize Backup Costs](https://azure.microsoft.com/en-us/blog/5-ways-to-optimize-your-backup-costs-with-azure-backup/)
- [Reserved Capacity Discounts](https://learn.microsoft.com/en-us/azure/backup/backup-azure-reserved-pricing-optimize-cost)

---

# SECURITY & IDENTITY

## 14. Key Vault

### Pricing Model
- **Standard Tier**:
  - Per vault per month charge (~$1-2/month)
  - Operations: $0.03 per 10K operations
  - Certificate operations separate
- **Premium Tier**:
  - Higher per-vault charge (~$10/month)
  - Hardware Security Module (HSM) support
  - Per-operation cost slightly higher
- **Operations Billing**:
  - Each get/set/delete/list = 1 operation
  - Key rotation, secret renewal = operation count
  - Caching on app-side reduces operations
- **Regional Pricing**: Slight variation by region

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| API Calls Per Hour | Spiking | Potential inefficiency |
| Secret/Key Count | Proliferation detected | Consolidation needed |
| Failed Operations | > 0.1% | Access control issue |
| Certificate Near Expiry | < 30 days | Renewal needed |
| Vault Access Rate | By IP tracked | Anomaly detection |
| Diagnostic Logging Volume | Growing | Storage cost increase |
| Operation Duration | > baseline | Performance issue |
| Deleted Vault Recovery Time | Approaching deadline | Consider retention |
| Key Rotation Frequency | Excessive | Unnecessary operations |
| Soft-Delete Recovery | Growing count | Cleanup needed |

### Cost Optimization Rules (with Savings %)
1. **Consolidate Vaults**: Reduce vault count; multiple vaults = multiple monthly charges. **Savings: 20-30%** per vault eliminated
2. **Implement Client-Side Caching**: Cache fetched secrets locally; reduces API calls. **Savings: 50-80%** through caching
3. **Batch Secret Updates**: Batch rotations rather than frequent individual updates. **Savings: 15-20%** through batching
4. **Use Standard Tier Unless HSM Required**: Premium only needed for hardware security. **Savings: 80%** on vault charge
5. **Set Appropriate Soft-Delete/Purge Policy**: Avoid retaining deleted items unnecessarily. **Savings: 10-15%** through cleanup

### Documentation URLs
- [Key Vault Pricing](https://azure.microsoft.com/en-us/pricing/details/key-vault/)
- [How to Estimate Key Vault Costs](https://learn.microsoft.com/en-us/answers/questions/5608202/how-to-correctly-estimate-azure-key-vault-cost)
- [Key Vault Overview](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)
- [Cost Optimization through Caching](https://learn.microsoft.com/en-us/answers/questions/1688971/cost-implications-of-azure-key-vault-with-diagnost)

---

## 15. Azure Sentinel

### Pricing Model
- **Pay-As-You-Go** (per GB):
  - Charged by GB of data ingested into Sentinel-enabled workspace
  - First 10 GB free per month
  - Per-GB rate decreases at higher volumes
- **Commitment Tiers** (volume-based):
  - 100 GB/day → 200 GB/day → 500 GB/day → 1 TB/day → 5 TB/day
  - Commitment provides 15-25% discount vs. pay-as-you-go
- **Data Lake Tier** (alternative):
  - Secondary data for non-real-time analytics
  - Significantly lower ingestion cost
  - Query cost per GB
- **Log Analytics Workspace Charges**: Additional to Sentinel (workspace ingestion + Sentinel tier)
- **Regional Pricing**: Varies slightly by region

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Daily Data Ingestion | Growing trend | Cost projection |
| Ingestion by Source | Identify top sources | Filtering opportunity |
| Analytics Tier Usage | > projected | Right-size commitment |
| Data Lake Ingestion | Unused | Cost waste |
| Hunting Query Costs | Excessive | Query optimization |
| Playbook Executions | Baseline variance | Automation audit |
| Alert Rules Count | Proliferation | Rule consolidation |
| Incident Creation Rate | Spiking | Alert tuning |
| User Licenses Active | Exceeding budget | Access control |
| Connector Health | Degradation | Data quality issue |

### Cost Optimization Rules (with Savings %)
1. **Use Data Lake for Secondary/Non-Real-Time Data**: 50-80% cheaper than analytics tier. **Savings: 50-80%** for historical data
2. **Separate Non-Security Data**: Data in non-Sentinel workspace costs less. **Savings: 25-35%** by removing non-security telemetry
3. **Commit to Tier if > 100GB/day**: Commitment tier discount pays for itself. **Savings: 15-25%** through commitment
4. **Implement Collection Rules**: Filter at source to reduce ingestion. **Savings: 30-50%** through source filtering
5. **Consolidate Data Workspaces**: Separate workspace per team = waste. **Savings: 20-40%** through consolidation

### Documentation URLs
- [Plan Costs & Understand Pricing - Sentinel](https://learn.microsoft.com/en-us/azure/sentinel/billing)
- [Microsoft Sentinel Pricing](https://azure.microsoft.com/en-us/pricing/details/microsoft-sentinel/)
- [Manage & Monitor Costs - Sentinel](https://learn.microsoft.com/en-us/azure/sentinel/billing-monitor-costs)
- [Reduce Costs for Sentinel](https://learn.microsoft.com/en-us/azure/sentinel/billing-reduce-costs)

---

# ANALYTICS

## 16. Power BI

### Pricing Model
- **Power BI Pro License**:
  - $10/month per user (annual commitment)
  - Includes desktop, cloud, mobile
  - Share content with other Pro users
- **Power BI Premium Per User**:
  - $20/month per user
  - Enhanced capacity; higher refresh rates
  - Newer licensing model
- **Power BI Premium Capacity**:
  - Fixed cost based on sku (P1-P5, ranging $5K-$40K+/month)
  - Shared across unlimited users
  - Best for large enterprises
- **Power BI Embedded**:
  - Consumption-based; $0.64-$2.56/hour per vCore
  - Integrated into applications
- **Dataflow Storage**: Additional charge per GB used

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| User License Count | Unused seats | Cost waste |
| Refresh Frequency | Excessive | Schedule optimization |
| Data Model Size | Growing rapidly | Compression needed |
| Premium Capacity CPU | > 80% sustained | Upgrade needed |
| Premium Capacity Memory | > 85% | Scale up |
| Dataflow Execution Time | Trending up | Query optimization |
| Import Size | Exponential growth | DirectQuery consideration |
| Premium Capacity Throughput | Exceeding baseline | Query pattern review |
| Audit Log Retention | Excessive storage | Retention policy |
| Embedded Request Count | Rapid growth | Cost projection |

### Cost Optimization Rules (with Savings %)
1. **Power BI Premium Only for > 50 Users**: Break-even point; below = Pro licenses cheaper. **Savings: 40-60%** using Pro only for small teams
2. **Consolidate Workspaces**: Reduce workspace count; per-workspace overhead. **Savings: 15-25%** through consolidation
3. **Use DirectQuery for Large Datasets**: Eliminates import refresh cost. **Savings: 30-40%** for frequently refreshed large tables
4. **Implement Aggregation Tables**: Reduce query load on base tables. **Savings: 20-30%** through aggregations
5. **Remove Unused Reports/Dashboards**: Eliminate unused licenses attached to deleted content. **Savings: 10-20%** through cleanup

### Documentation URLs
- [Power BI Pricing](https://www.microsoft.com/en-us/power-platform/products/power-bi/pricing)
- [Analyze Azure Costs with Power BI App](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/analyze-cost-data-azure-cost-management-power-bi-template-app)
- [Optimize Costs with Data Analysis](https://learn.microsoft.com/en-us/training/modules/optimize-costs-data-analysis-powerbi/)
- [Power BI Embedded Pricing](https://azure.microsoft.com/en-us/pricing/details/power-bi-embedded/)

---

## 17. Azure Data Explorer

### Pricing Model
- **Engine Nodes** (compute):
  - Hourly charge per node type (D11-L4 SKU range)
  - Higher SKU = higher cost but better performance
  - Billed for node count × hours active
- **Cluster Markup**: Service markup on top of VM cost
- **Storage**:
  - Per GB per month for hot storage
  - Cheaper storage tiers for archive
- **Ingestion**: Free; included in engine cost
- **Queries**: Free; included in engine cost
- **Auto-Scale Options**: Scale up/down based on demand; saves cost during low-traffic periods

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| CPU Percentage | > 80% sustained | Scale up nodes |
| Memory Percentage | > 85% | Near capacity |
| Disk Utilization | > 80% | Retention/cleanup |
| Query Duration | > baseline | Query optimization |
| Ingestion Throughput | Below expected | Data source issue |
| Cluster Node Count | Growing steadily | Analyze workload |
| Cache Hit Ratio | < 70% | Query pattern issue |
| Data Retention Per Table | Unbounded growth | Retention policy |
| Unused Tables | Detected | Consolidation |
| Cluster Downtime | Any duration | Availability review |

### Cost Optimization Rules (with Savings %)
1. **Enable Auto-Scale**: Scales down during low-traffic periods. **Savings: 30-50%** for variable workloads
2. **Use Smaller Node Types**: Start with D13, scale up only if needed. **Savings: 40-60%** through right-sizing
3. **Implement Materialized Views**: Pre-compute expensive aggregations. **Savings: 20-40%** by reducing query compute
4. **Set Table Retention**: Auto-purge old data; reduce storage footprint. **Savings: 15-30%** through retention policy
5. **Use Event Grid Ingestion**: Cheaper than Event Hubs for high-volume. **Savings: 50-70%** by using cheaper ingestion path

### Documentation URLs
- [Azure Data Explorer Pricing](https://azure.microsoft.com/en-us/pricing/details/data-explorer/)
- [Cost Per GB Ingested](https://learn.microsoft.com/en-us/azure/data-explorer/pricing-cost-drivers)
- [Pricing Calculator](https://learn.microsoft.com/en-us/azure/data-explorer/pricing-calculator)
- [Cost Optimization Recommendations](https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations)

---

# NETWORKING - ADDITIONAL

## 18. Azure VPN Gateway

### Pricing Model
- **Gateway SKU Charges** (hourly):
  - Basic: Lowest cost (~$0.04/hour)
  - Standard: Mid-tier (~$0.08/hour)
  - High Performance/VpnGw1-VpnGw5: Premium (~$0.12-$0.40/hour)
- **Billing Components**:
  - Gateway compute (always charges while deployed)
  - Data transfer egress (per GB out)
  - Inbound data transfer: Free
- **Regional Pricing**: Varies by Azure region
- **Data Transfer Costs**: $0.035-$0.12/GB depending on destination zone

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Tunnel Status | Any disconnection | Connectivity issue |
| Bandwidth Usage | Trending up | Capacity planning |
| Data Transfer Volume | Spiking | Cost projection |
| Egress Rate | Exceeding baseline | Unexpected traffic |
| P2S Connection Count | > 80% max | Scaling needed |
| S2S Connection Count | Approaching limit | Tunnel overflow |
| BGP Status | Down/Unstable | Routing issue |
| Gateway Latency | > 50ms | Performance issue |
| CPU Utilization | > 75% | Upgrade needed |
| Packet Loss | > 0% | Network quality |

### Cost Optimization Rules (with Savings %)
1. **Use Lowest Adequate SKU**: Basic for simple connectivity, Standard for moderate. **Savings: 50-75%** vs. premium when not needed
2. **Consolidate VPN Gateways**: Shared gateway across VNets saves repeated costs. **Savings: 30-60%** through gateway sharing
3. **Delete Unused Gateways**: Gateway charges even when idle; remove if not used. **Savings: 100%** on removed gateways
4. **Monitor Egress Data**: Consolidate outbound traffic; minimize inter-region transfers. **Savings: 20-40%** through consolidation
5. **Avoid Multi-Region If Single Sufficient**: Multi-region = multiple gateways = multiple charges. **Savings: 50%** by staying single-region

### Documentation URLs
- [VPN Gateway Pricing](https://azure.microsoft.com/en-us/pricing/details/vpn-gateway/)
- [Virtual Network Cost Optimization](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-cost-optimization)
- [About Virtual WAN Pricing](https://learn.microsoft.com/en-us/azure/virtual-wan/pricing-concepts)
- [VPN Gateway Overview](https://learn.microsoft.com/en-us/azure/vpn-gateway/vpn-gateway-about-vpngateways)

---

## 19. Azure ExpressRoute

### Pricing Model
- **Circuit Fee** (monthly):
  - Local SKU: Access to regions within metro area
  - Standard SKU: Regional access; fixed fee per month
  - Premium SKU: Global access; higher monthly fee
- **Port Fee** (monthly):
  - Covers dedicated connectivity
  - Based on peering location and provider
- **Data Transfer** (per GB):
  - Inbound: Free
  - Outbound: Charged per GB by zone
  - Global Reach: Extra charge for cross-region connectivity
- **Regional Pricing**: Varies by peering location and SKU
- **Metered vs. Unlimited**: Standard/Premium allow both; Local = always unlimited

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Circuit Availability | < 99.95% | Reliability issue |
| BGP Session Status | Down/Unstable | Routing issue |
| Primary/Secondary Path Bandwidth | Imbalanced | Load distribution |
| Outbound Data Transfer | Trending rapidly | Cost projection |
| Global Reach Utilization | Growing | Cost multiplier |
| Route Advertisement Count | Increasing | Routing complexity |
| Connection Errors | > baseline | Stability issue |
| Peering Location Latency | > baseline | Performance issue |
| Interface Status | Any degradation | Physical issue |
| Virtual Network Gateway Throughput | > 80% | Scale up needed |

### Cost Optimization Rules (with Savings %)
1. **Use Local SKU for Metro-Area Only**: Lowest cost if regional scope sufficient. **Savings: 50-60%** vs. Standard/Premium
2. **Metered Data Plan for Low-Traffic**: Unlimited only if > 50GB/month egress. **Savings: 40-60%** with metered for low-traffic
3. **Avoid Global Reach Unless Necessary**: Cross-region connectivity premium. **Savings: 30-50%** by staying single-region
4. **Consolidate Multiple Circuits**: Fewer circuits = fewer monthly fees. **Savings: 25-40%** through consolidation
5. **Monitor Egress Closely**: Track by destination zone; minimize inter-zone traffic. **Savings: 20-35%** through data consolidation

### Documentation URLs
- [ExpressRoute Pricing](https://azure.microsoft.com/en-us/pricing/details/expressroute/)
- [Plan & Manage Costs - ExpressRoute](https://learn.microsoft.com/en-us/azure/expressroute/plan-manage-cost)
- [Architecture Best Practices - ExpressRoute](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-expressroute)
- [Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/)

---

## 20. CDN / Front Door / Traffic Manager

### Pricing Model

#### Azure CDN (Classic)
- **Per-GB Egress**: Primary cost (varies by provider/tier)
  - Standard Microsoft: ~$0.087/GB
  - Premium Verizon: Higher per-GB, better performance
- **Requests**: Additional charge (~$0.05 per 10K requests)
- **Zones**: Different regions = different per-GB rates
- **Deprecation**: CDN Standard Microsoft retiring Sept 30, 2027

#### Azure Front Door (Standard/Premium)
- **Base Fee** (per profile per month):
  - Standard: ~$0.60/month
  - Premium: ~$30/month
- **Requests**:
  - Billed per million requests
  - Incoming requests: Primary cost
  - Data transfer (if uncached): Secondary cost
- **Web Application Firewall** (optional):
  - Per-rule pricing (~$1-2 per rule/month)
  - Bot manager separate charge

#### Traffic Manager
- **DNS Queries**: $0.50 per million DNS queries
- **Health Probes**: Extra per probe
- **Low cost** for global load balancing

### Azure Monitor Metrics (Top 5-10)
| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Egress Bandwidth | Trending rapidly | Cost projection |
| Cache Hit Ratio | < 70% | Caching policy review |
| Origin Requests | > expected | Cache effectiveness |
| Request Count | Spiking | Capacity/cost alert |
| WAF Triggered Events | > baseline | Security review |
| Bot Traffic Percentage | > 5% | Bot challenge rules |
| Origin Latency | > baseline | Origin issue |
| SSL/TLS Handshake Failures | > 0.1% | Certificate issue |
| Geo-Distribution of Traffic | Unexpected spikes | DDoS check |
| Data Transfer by Zone | Expensive zones | Cost optimization |

### Cost Optimization Rules (with Savings %)
1. **Cache Aggressively**: Increase TTL where possible; cached = no origin requests. **Savings: 40-70%** through caching
2. **Use Front Door Standard vs. Premium**: Premium only for advanced features. **Savings: 95%** using Standard
3. **Consolidate Origins**: Fewer origins = fewer health probes. **Savings: 10-15%** through consolidation
4. **Compress Responses**: Enable compression at Front Door level. **Savings: 20-40%** through compression
5. **Replace CDN with Front Door**: Front Door cheaper for most use cases. **Savings: 30-50%** by migrating CDN to Front Door

### Documentation URLs
- [Front Door Pricing](https://azure.microsoft.com/en-us/pricing/details/frontdoor/)
- [CDN Pricing](https://azure.microsoft.com/en-us/pricing/details/cdn/)
- [Compare CDN & Front Door Pricing](https://learn.microsoft.com/en-us/azure/frontdoor/compare-cdn-front-door-price)
- [Traffic Manager Pricing](https://azure.microsoft.com/en-us/pricing/details/traffic-manager/)

---

# COST OPTIMIZATION SUMMARY TABLE

| Resource | Biggest Cost Driver | #1 Optimization | Typical Savings |
|----------|------------------|-----------------|-----------------|
| **SQL Database** | Compute (vCore-hours) | Use Serverless tier for idle periods | 40-60% |
| **MySQL** | Compute + Storage | Use Burstable tier + RI | 40-50% |
| **Synapse** | DWU Hours + Storage | Enable auto-pause + rightsize | 40-60% |
| **Data Factory** | DIU Hours | Use Self-Hosted IR | 40-60% |
| **Stream Analytics** | SU-hours | Migrate to v2 + right-size | 50% |
| **Cognitive Search** | Search Units | Use Serverless for dev | 70-90% |
| **Event Hubs** | Throughput Units | Use Basic tier + manual scale | 50% |
| **Service Bus** | Operations | Implement long-polling | 40-60% |
| **API Management** | Service units | Use Consumption tier | 50-80% |
| **Logic Apps** | Action executions | Use Standard plan for volume | 40-60% |
| **App Insights** | Data ingestion | Implement sampling | 50-90% |
| **Log Analytics** | Data ingestion | Use commitment tiers | 20-30% |
| **Backup** | Storage consumed | Selective disk backup | 30-50% |
| **Key Vault** | Monthly vault fee | Consolidate vaults | 20-30% |
| **Sentinel** | Data ingestion | Use Data Lake tier | 50-80% |
| **Power BI** | License cost | Use Pro vs. Premium | 40-60% |
| **Data Explorer** | Engine nodes | Enable auto-scale | 30-50% |
| **VPN Gateway** | Gateway SKU hourly | Use lowest adequate SKU | 50-75% |
| **ExpressRoute** | Circuit + egress | Use Local SKU if possible | 50-60% |
| **Front Door** | Egress + requests | Cache aggressively | 40-70% |

---

# KEY RECOMMENDATIONS ACROSS ALL SERVICES

## Universal Cost Optimization Principles

1. **Measure Everything**: Enable monitoring/logging FIRST before optimizing
2. **Right-Size for Actual Demand**: Start small; scale up only when needed
3. **Use Commitment Tiers**: 1-year minimums provide 20-35% discount across most services
4. **Consolidation**: Fewer resources = fewer management/licensing fees
5. **Automate Scaling**: Auto-pause/scale-down during off-hours
6. **Archive Old Data**: Long-term retention storage is 80-90% cheaper
7. **Filter at Source**: Reduce data collection volume before storage
8. **Reserved Instances**: 33-55% savings for committed capacity workloads
9. **Hybrid Benefits**: Use existing Microsoft licenses (SQL, Windows)
10. **Avoid Idle Resources**: Delete unused resources; paused still charges in some cases

---

## Azure Pricing Calculator & Tools
- **Main Calculator**: https://azure.microsoft.com/en-us/pricing/calculator
- **Azure Cost Management**: https://portal.azure.com (search "Cost Management")
- **Azure Advisor**: Automated recommendations in portal
- **TCO Calculator**: https://azure.microsoft.com/en-us/pricing/tco/calculator/

---

**Last Updated**: July 2026  
**Data Source**: Official Microsoft Learn Documentation, Azure Pricing Pages, Well-Architected Framework

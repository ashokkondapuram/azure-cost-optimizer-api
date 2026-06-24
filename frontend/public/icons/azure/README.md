# Azure service icons (cluster stat chips)

These SVGs are **Microsoft Azure portal / architecture** style service icons, vendored for **`workloads.html`** cluster summary chips. The UI loads them from **`/static/icons/azure/*.svg`** (same `static/` tree as the app).

## Source

Files were obtained from the community mirror **[maskati/azure-icons](https://github.com/maskati/azure-icons)**, which tracks assets aligned with the official **[Azure Architecture Icons](https://learn.microsoft.com/en-us/azure/architecture/icons/)** program.

Use remains subject to **Microsoft’s terms** for those icons (diagrams, documentation, and solution design—verify fit for your product context).

## Mapping (filename → use in UI)

| File | Azure concept |
|------|----------------|
| `resource-groups.svg` | Resource groups |
| `subscription.svg` | Subscription |
| `managed-clusters.svg` | Kubernetes / AKS managed clusters |
| `global-view.svg` | Region / multi-region (Global view) |
| `virtual-machine-scale-set.svg` | Scale sets / node pools |
| `virtual-machine.svg` | Virtual machines / nodes |
| `container-group.svg` | Container groups / workload units |
| `all-virtual-machines.svg` | Aggregate compute (alloc vCPU) |
| `storage-cache.svg` | Azure HPC Cache (used as memory proxy) |
| `cost-management.svg` | Cost management |

To refresh from upstream, replace each file with the same path under  
`https://raw.githubusercontent.com/maskati/azure-icons/main/svg/…`  
(e.g. `svg/HubsExtension/ResourceGroups.svg` → `resource-groups.svg`).

// ─── Subscriptions ───────────────────────────────────────────────────────────
export const mockSubscriptions = [
  { id: 'sub-prod-001',  name: 'Production',  env: 'prod',    budget: 15000 },
  { id: 'sub-stage-002', name: 'Staging',     env: 'staging', budget: 5000  },
  { id: 'sub-dev-003',   name: 'Development', env: 'dev',     budget: 2000  },
];

// ─── Costs per subscription ──────────────────────────────────────────────────
export const mockCostsBySubscription = {
  'sub-prod-001': {
    total: 12840.50,
    rows: [
      [20260601,820,'rg-prod-app'],[20260602,745,'rg-prod-app'],[20260603,910,'rg-prod-data'],
      [20260604,680,'rg-prod-data'],[20260605,530,'rg-prod-network'],[20260606,1020,'rg-prod-app'],
      [20260607,890,'rg-prod-app'],[20260608,760,'rg-prod-data'],[20260609,490,'rg-prod-network'],
      [20260610,1140,'rg-prod-app'],[20260611,970,'rg-prod-data'],[20260612,420,'rg-prod-network'],
      [20260613,1050,'rg-prod-app'],[20260614,880,'rg-prod-data'],[20260615,510,'rg-prod-network'],
    ],
  },
  'sub-stage-002': {
    total: 3210.75,
    rows: [
      [20260601,180,'rg-stage-app'],[20260602,210,'rg-stage-app'],[20260603,195,'rg-stage-data'],
      [20260604,220,'rg-stage-data'],[20260605,175,'rg-stage-app'],[20260606,240,'rg-stage-app'],
      [20260607,200,'rg-stage-data'],[20260608,190,'rg-stage-app'],[20260609,215,'rg-stage-data'],
      [20260610,230,'rg-stage-app'],[20260611,185,'rg-stage-app'],[20260612,170,'rg-stage-data'],
      [20260613,250,'rg-stage-app'],[20260614,205,'rg-stage-data'],[20260615,145,'rg-stage-app'],
    ],
  },
  'sub-dev-003': {
    total: 870.20,
    rows: [
      [20260601,48,'rg-dev'],[20260602,62,'rg-dev'],[20260603,55,'rg-dev'],
      [20260604,70,'rg-dev'],[20260605,44,'rg-dev'],[20260606,80,'rg-dev'],
      [20260607,58,'rg-dev'],[20260608,67,'rg-dev'],[20260609,43,'rg-dev'],
      [20260610,90,'rg-dev'],[20260611,72,'rg-dev'],[20260612,38,'rg-dev'],
      [20260613,85,'rg-dev'],[20260614,59,'rg-dev'],[20260615,49,'rg-dev'],
    ],
  },
};

// ─── Resources ───────────────────────────────────────────────────────────────
export const mockResources = [
  // Compute
  { name:'vm-prod-web-01',    type:'Microsoft.Compute/virtualMachines',         location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Running',  sku:'Standard_D4s_v3', cost: 320 },
  { name:'vm-prod-web-02',    type:'Microsoft.Compute/virtualMachines',         location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Running',  sku:'Standard_D4s_v3', cost: 320 },
  { name:'vm-prod-api-01',    type:'Microsoft.Compute/virtualMachines',         location:'eastus',        rg:'rg-prod-app',     sub:'sub-prod-001', status:'Running',  sku:'Standard_D8s_v3', cost: 580 },
  { name:'vm-stage-01',       type:'Microsoft.Compute/virtualMachines',         location:'canadacentral', rg:'rg-stage-app',    sub:'sub-stage-002',status:'Running',  sku:'Standard_B2s',    cost: 80  },
  { name:'vm-dev-01',         type:'Microsoft.Compute/virtualMachines',         location:'canadacentral', rg:'rg-dev',          sub:'sub-dev-003',  status:'Stopped',  sku:'Standard_B1s',    cost: 12  },
  // AKS
  { name:'aks-prod-primary',  type:'Microsoft.ContainerService/managedClusters',location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Running',  sku:'Standard',        cost:1200 },
  { name:'aks-prod-secondary',type:'Microsoft.ContainerService/managedClusters',location:'eastus',        rg:'rg-prod-app',     sub:'sub-prod-001', status:'Running',  sku:'Standard',        cost:1100 },
  { name:'aks-stage-01',      type:'Microsoft.ContainerService/managedClusters',location:'canadacentral', rg:'rg-stage-app',    sub:'sub-stage-002',status:'Running',  sku:'Free',            cost: 280 },
  // Storage
  { name:'stproddata01',      type:'Microsoft.Storage/storageAccounts',         location:'canadacentral', rg:'rg-prod-data',    sub:'sub-prod-001', status:'Active',   sku:'Standard_LRS',    cost: 145 },
  { name:'stprodbackup01',    type:'Microsoft.Storage/storageAccounts',         location:'eastus',        rg:'rg-prod-data',    sub:'sub-prod-001', status:'Active',   sku:'Standard_GRS',    cost: 210 },
  { name:'ststagedata01',     type:'Microsoft.Storage/storageAccounts',         location:'canadacentral', rg:'rg-stage-data',   sub:'sub-stage-002',status:'Active',   sku:'Standard_LRS',    cost: 55  },
  { name:'stdev01',           type:'Microsoft.Storage/storageAccounts',         location:'canadacentral', rg:'rg-dev',          sub:'sub-dev-003',  status:'Active',   sku:'Standard_LRS',    cost: 18  },
  // App Services
  { name:'app-prod-api',      type:'Microsoft.Web/sites',                       location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Running',  sku:'P2v3',            cost: 320 },
  { name:'app-prod-frontend', type:'Microsoft.Web/sites',                       location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Running',  sku:'P1v3',            cost: 160 },
  { name:'app-stage-api',     type:'Microsoft.Web/sites',                       location:'canadacentral', rg:'rg-stage-app',    sub:'sub-stage-002',status:'Running',  sku:'B2',              cost: 75  },
  // SQL
  { name:'sql-prod-primary',  type:'Microsoft.Sql/servers',                     location:'canadacentral', rg:'rg-prod-data',    sub:'sub-prod-001', status:'Online',   sku:'BusinessCritical', cost: 890 },
  { name:'sql-prod-replica',  type:'Microsoft.Sql/servers',                     location:'eastus',        rg:'rg-prod-data',    sub:'sub-prod-001', status:'Online',   sku:'BusinessCritical', cost: 890 },
  { name:'sql-stage',         type:'Microsoft.Sql/servers',                     location:'canadacentral', rg:'rg-stage-data',   sub:'sub-stage-002',status:'Online',   sku:'GeneralPurpose',   cost: 210 },
  // PostgreSQL
  { name:'pg-prod-cost-db',   type:'Microsoft.DBforPostgreSQL/flexibleServers',  location:'canadacentral', rg:'rg-prod-data',    sub:'sub-prod-001', status:'Running',  sku:'Standard_D4s_v3', cost: 380 },
  // Disks
  { name:'disk-vm-prod-01',   type:'Microsoft.Compute/disks',                   location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Attached', sku:'Premium_LRS',     cost: 65  },
  { name:'disk-vm-prod-02',   type:'Microsoft.Compute/disks',                   location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Attached', sku:'Premium_LRS',     cost: 65  },
  { name:'disk-unattached-01',type:'Microsoft.Compute/disks',                   location:'eastus',        rg:'rg-prod-app',     sub:'sub-prod-001', status:'Unattached',sku:'Standard_LRS',   cost: 12  },
  // Key Vaults
  { name:'kv-prod-secrets',   type:'Microsoft.KeyVault/vaults',                 location:'canadacentral', rg:'rg-prod-app',     sub:'sub-prod-001', status:'Active',   sku:'Standard',        cost: 8   },
  { name:'kv-stage-secrets',  type:'Microsoft.KeyVault/vaults',                 location:'canadacentral', rg:'rg-stage-app',    sub:'sub-stage-002',status:'Active',   sku:'Standard',        cost: 4   },
  // Public IPs
  { name:'pip-prod-lb-01',    type:'Microsoft.Network/publicIPAddresses',        location:'canadacentral', rg:'rg-prod-network', sub:'sub-prod-001', status:'Associated',sku:'Standard',       cost: 15  },
  { name:'pip-prod-agw',      type:'Microsoft.Network/publicIPAddresses',        location:'canadacentral', rg:'rg-prod-network', sub:'sub-prod-001', status:'Associated',sku:'Standard',       cost: 15  },
  { name:'pip-unassigned-01', type:'Microsoft.Network/publicIPAddresses',        location:'eastus',        rg:'rg-prod-network', sub:'sub-prod-001', status:'Unassigned',sku:'Standard',       cost: 4   },
];

// ─── Kubernetes clusters ──────────────────────────────────────────────────────
export const mockClusters = [
  { name:'aks-prod-primary',   sub:'sub-prod-001', env:'prod',    location:'canadacentral', nodeCount:6, k8sVersion:'1.29.2', status:'Running' },
  { name:'aks-prod-secondary', sub:'sub-prod-001', env:'prod',    location:'eastus',        nodeCount:4, k8sVersion:'1.29.2', status:'Running' },
  { name:'aks-stage-01',       sub:'sub-stage-002',env:'staging', location:'canadacentral', nodeCount:2, k8sVersion:'1.28.5', status:'Running' },
];

export const mockK8s = [
  // aks-prod-primary nodes
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-01', pod:null, namespace:null,       cpu:'620m', memory:'3.8Gi', cpuPct:62, memPct:76, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-02', pod:null, namespace:null,       cpu:'480m', memory:'2.9Gi', cpuPct:48, memPct:58, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-03', pod:null, namespace:null,       cpu:'710m', memory:'4.2Gi', cpuPct:71, memPct:84, recorded_at:'2026-06-22 14:30:00' },
  // aks-prod-primary pods
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-01', pod:'cost-api-7d9f4b',       namespace:'default',    cpu:'180m', memory:'320Mi', cpuPct:18, memPct:32, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-01', pod:'frontend-5c8b2a',       namespace:'default',    cpu:'95m',  memory:'128Mi', cpuPct:10, memPct:13, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-02', pod:'postgres-0',            namespace:'database',   cpu:'240m', memory:'512Mi', cpuPct:24, memPct:51, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-02', pod:'redis-master-0',        namespace:'cache',      cpu:'120m', memory:'256Mi', cpuPct:12, memPct:26, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-03', pod:'util-agent-2x4p',       namespace:'monitoring', cpu:'35m',  memory:'64Mi',  cpuPct:4,  memPct:6,  recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-primary',  node:'aks-nodepool-prod-03', pod:'prometheus-server-0',   namespace:'monitoring', cpu:'310m', memory:'1.1Gi', cpuPct:31, memPct:22, recorded_at:'2026-06-22 14:30:00' },
  // aks-prod-secondary nodes
  { cluster:'aks-prod-secondary',node:'aks-nodepool-sec-01',  pod:null, namespace:null,       cpu:'390m', memory:'2.1Gi', cpuPct:39, memPct:42, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-secondary',node:'aks-nodepool-sec-02',  pod:null, namespace:null,       cpu:'530m', memory:'3.0Gi', cpuPct:53, memPct:60, recorded_at:'2026-06-22 14:30:00' },
  // aks-prod-secondary pods
  { cluster:'aks-prod-secondary',node:'aks-nodepool-sec-01',  pod:'cost-api-replica-9b2c', namespace:'default',    cpu:'155m', memory:'290Mi', cpuPct:16, memPct:29, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-prod-secondary',node:'aks-nodepool-sec-02',  pod:'worker-jobs-4f7a',      namespace:'jobs',       cpu:'280m', memory:'480Mi', cpuPct:28, memPct:48, recorded_at:'2026-06-22 14:30:00' },
  // aks-stage-01 nodes
  { cluster:'aks-stage-01',      node:'aks-nodepool-stage-01',pod:null, namespace:null,       cpu:'210m', memory:'1.4Gi', cpuPct:21, memPct:28, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-stage-01',      node:'aks-nodepool-stage-02',pod:null, namespace:null,       cpu:'180m', memory:'1.1Gi', cpuPct:18, memPct:22, recorded_at:'2026-06-22 14:30:00' },
  // aks-stage-01 pods
  { cluster:'aks-stage-01',      node:'aks-nodepool-stage-01',pod:'cost-api-stage-3d1b',   namespace:'default',    cpu:'90m',  memory:'180Mi', cpuPct:9,  memPct:18, recorded_at:'2026-06-22 14:30:00' },
  { cluster:'aks-stage-01',      node:'aks-nodepool-stage-02',pod:'frontend-stage-8e2c',   namespace:'default',    cpu:'60m',  memory:'96Mi',  cpuPct:6,  memPct:10, recorded_at:'2026-06-22 14:30:00' },
];

export const mockHistory = [
  { id:'a1b2c3d4-0001', subscription_id:'sub-prod-001',  resource_group:'rg-prod-app',   timeframe:'MonthToDate',        created_at:'2026-06-22 14:00:00' },
  { id:'a1b2c3d4-0002', subscription_id:'sub-prod-001',  resource_group:'rg-prod-data',  timeframe:'MonthToDate',        created_at:'2026-06-22 13:45:00' },
  { id:'a1b2c3d4-0003', subscription_id:'sub-stage-002', resource_group:null,            timeframe:'TheLastMonth',       created_at:'2026-06-21 11:00:00' },
  { id:'a1b2c3d4-0004', subscription_id:'sub-dev-003',   resource_group:'rg-dev',        timeframe:'WeekToDate',         created_at:'2026-06-21 09:30:00' },
  { id:'a1b2c3d4-0005', subscription_id:'sub-prod-001',  resource_group:null,            timeframe:'BillingMonthToDate', created_at:'2026-06-20 08:00:00' },
];

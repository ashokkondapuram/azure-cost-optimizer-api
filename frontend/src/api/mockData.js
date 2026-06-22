export const mockCosts = {
  data: {
    columns: [
      { name: 'UsageDate' },
      { name: 'PreTaxCost' },
      { name: 'ResourceGroup' },
    ],
    rows: [
      [20260601, 142.50, 'rg-production'],
      [20260602, 98.20,  'rg-production'],
      [20260603, 210.75, 'rg-analytics'],
      [20260604, 185.00, 'rg-analytics'],
      [20260605, 76.40,  'rg-dev'],
      [20260606, 310.90, 'rg-production'],
      [20260607, 265.30, 'rg-production'],
      [20260608, 133.60, 'rg-analytics'],
      [20260609, 88.10,  'rg-dev'],
      [20260610, 412.00, 'rg-production'],
      [20260611, 198.50, 'rg-analytics'],
      [20260612, 54.30,  'rg-dev'],
      [20260613, 320.00, 'rg-production'],
      [20260614, 175.80, 'rg-analytics'],
      [20260615, 92.40,  'rg-dev'],
      [20260616, 289.60, 'rg-production'],
      [20260617, 144.20, 'rg-analytics'],
      [20260618, 67.90,  'rg-dev'],
      [20260619, 378.40, 'rg-production'],
      [20260620, 210.10, 'rg-analytics'],
      [20260621, 105.60, 'rg-dev'],
      [20260622, 450.30, 'rg-production'],
    ],
  },
};

export const mockResources = [
  { name: 'vm-prod-01',      type: 'Microsoft.Compute/virtualMachines',      location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'vm-prod-02',      type: 'Microsoft.Compute/virtualMachines',      location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'vm-analytics-01', type: 'Microsoft.Compute/virtualMachines',      location: 'eastus',        id: '/subscriptions/xxx/resourceGroups/rg-analytics/providers/...' },
  { name: 'aks-prod-cluster',type: 'Microsoft.ContainerService/managedClusters', location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'stproddata01',    type: 'Microsoft.Storage/storageAccounts',      location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'stanalytics01',   type: 'Microsoft.Storage/storageAccounts',      location: 'eastus',        id: '/subscriptions/xxx/resourceGroups/rg-analytics/providers/...' },
  { name: 'app-cost-api',    type: 'Microsoft.Web/sites',                    location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'app-frontend',    type: 'Microsoft.Web/sites',                    location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'sql-prod-server', type: 'Microsoft.Sql/servers',                  location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'disk-vm-prod-01', type: 'Microsoft.Compute/disks',                location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'kv-prod-secrets', type: 'Microsoft.KeyVault/vaults',              location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'pip-prod-lb',     type: 'Microsoft.Network/publicIPAddresses',    location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
  { name: 'pg-cost-db',      type: 'Microsoft.DBforPostgreSQL/flexibleServers', location: 'canadacentral', id: '/subscriptions/xxx/resourceGroups/rg-production/providers/...' },
];

export const mockK8s = [
  { id:'1', cluster:'aks-prod-cluster', node:'aks-nodepool-01', pod:null,              namespace:null,       cpu:'320m',  memory:'1.2Gi', recorded_at:'2026-06-22 10:00:00' },
  { id:'2', cluster:'aks-prod-cluster', node:'aks-nodepool-02', pod:null,              namespace:null,       cpu:'410m',  memory:'2.1Gi', recorded_at:'2026-06-22 10:00:00' },
  { id:'3', cluster:'aks-prod-cluster', node:'aks-nodepool-01', pod:'cost-api-7d9f',   namespace:'default',  cpu:'120m',  memory:'256Mi', recorded_at:'2026-06-22 10:00:00' },
  { id:'4', cluster:'aks-prod-cluster', node:'aks-nodepool-01', pod:'frontend-5c8b',   namespace:'default',  cpu:'80m',   memory:'128Mi', recorded_at:'2026-06-22 10:00:00' },
  { id:'5', cluster:'aks-prod-cluster', node:'aks-nodepool-02', pod:'util-agent-2x4p', namespace:'monitoring',cpu:'30m',  memory:'48Mi',  recorded_at:'2026-06-22 10:00:00' },
  { id:'6', cluster:'aks-prod-cluster', node:'aks-nodepool-02', pod:'postgres-0',       namespace:'database', cpu:'210m',  memory:'512Mi', recorded_at:'2026-06-22 10:00:00' },
];

export const mockHistory = [
  { id:'a1b2c3d4-0001', subscription_id:'xxxxxxxx-0001', resource_group:'rg-production', timeframe:'MonthToDate',        created_at:'2026-06-22 09:00:00' },
  { id:'a1b2c3d4-0002', subscription_id:'xxxxxxxx-0001', resource_group:'rg-analytics',  timeframe:'MonthToDate',        created_at:'2026-06-22 09:15:00' },
  { id:'a1b2c3d4-0003', subscription_id:'xxxxxxxx-0001', resource_group:null,            timeframe:'TheLastMonth',       created_at:'2026-06-21 14:00:00' },
  { id:'a1b2c3d4-0004', subscription_id:'xxxxxxxx-0001', resource_group:'rg-dev',        timeframe:'WeekToDate',         created_at:'2026-06-21 11:30:00' },
  { id:'a1b2c3d4-0005', subscription_id:'xxxxxxxx-0001', resource_group:null,            timeframe:'BillingMonthToDate', created_at:'2026-06-20 08:45:00' },
];

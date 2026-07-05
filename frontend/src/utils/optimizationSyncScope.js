/**
 * Scoped sync/analysis options for Optimization center.
 * Categories align with sidebar nav groups; resources mirror component_map.py.
 */

import { NAV_RESOURCE_GROUPS, syncTypesForNavGroup } from '../config/appRegistry';

/** Resource page id → optimization engine component label. */
const RESOURCE_COMPONENTS = {
  vms: 'Virtual Machines',
  vmss: 'Virtual Machine Scale Sets',
  disks: 'Managed Disks',
  snapshots: 'Disk Snapshots',
  aks: 'AKS',
  acr: 'Container Registry',
  appservices: 'App Service',
  storage: 'Storage Accounts',
  publicips: 'Public IPs',
  loadbalancers: 'Load Balancers',
  appgateways: 'Application Gateways',
  nsgs: 'Network Security Groups',
  sql: 'SQL Database',
  cosmosdb: 'Cosmos DB',
  postgresql: 'PostgreSQL',
  keyvaults: 'Key Vault',
};

const RESOURCE_SCOPES = [
  { id: 'Virtual Machines', label: 'Virtual machines', syncTypes: ['compute/vm'], components: ['Virtual Machines'] },
  { id: 'Virtual Machine Scale Sets', label: 'VM scale sets', syncTypes: ['compute/vmss'], components: ['Virtual Machine Scale Sets'] },
  { id: 'Managed Disks', label: 'Managed disks', syncTypes: ['compute/disk'], components: ['Managed Disks'] },
  { id: 'Disk Snapshots', label: 'Disk snapshots', syncTypes: ['compute/snapshot'], components: ['Disk Snapshots'] },
  { id: 'AKS', label: 'AKS', syncTypes: ['containers/aks'], components: ['AKS'] },
  { id: 'App Service', label: 'App Service', syncTypes: ['appservice/webapp', 'appservice/plan'], components: ['App Service'] },
  { id: 'Storage Accounts', label: 'Storage accounts', syncTypes: ['storage/account'], components: ['Storage Accounts'] },
  { id: 'Public IPs', label: 'Public IPs', syncTypes: ['network/publicip'], components: ['Public IPs'] },
  { id: 'Network Interfaces', label: 'Network interfaces', syncTypes: ['network/nic'], components: ['Network Interfaces'] },
  { id: 'NAT Gateways', label: 'NAT gateways', syncTypes: ['network/nat'], components: ['NAT Gateways'] },
  { id: 'Private endpoints', label: 'Private endpoints', syncTypes: ['network/privateendpoint'], components: ['Networking'] },
  { id: 'Private link services', label: 'Private link services', syncTypes: ['network/privatelinkservice'], components: ['Networking'] },
  { id: 'Private DNS zones', label: 'Private DNS zones', syncTypes: ['network/privatedns'], components: ['Networking'] },
  { id: 'Virtual networks', label: 'Virtual networks', syncTypes: ['network/vnet'], components: ['Networking'] },
  { id: 'Network Security Groups', label: 'Network security groups', syncTypes: ['network/nsg'], components: ['Network Security Groups'] },
  { id: 'Load Balancers', label: 'Load balancers', syncTypes: ['network/loadbalancer'], components: ['Load Balancers'] },
  { id: 'Application Gateways', label: 'Application gateways', syncTypes: ['network/appgateway'], components: ['Application Gateways'] },
  { id: 'SQL Database', label: 'SQL Database', syncTypes: ['database/sql'], components: ['SQL Database'] },
  { id: 'PostgreSQL', label: 'PostgreSQL', syncTypes: ['database/postgresql'], components: ['PostgreSQL'] },
  { id: 'Cosmos DB', label: 'Cosmos DB', syncTypes: ['database/cosmosdb'], components: ['Cosmos DB'] },
  { id: 'Redis Cache', label: 'Redis Cache', syncTypes: ['database/redis'], components: ['Redis Cache'] },
  { id: 'Container Registry', label: 'Container registry', syncTypes: ['containers/acr'], components: ['Container Registry'] },
  { id: 'Key Vault', label: 'Key Vault', syncTypes: ['security/keyvault'], components: ['Key Vault'] },
];

function componentsForResourceIds(resourceIds) {
  const comps = new Set();
  for (const id of resourceIds || []) {
    const comp = RESOURCE_COMPONENTS[id];
    if (comp) comps.add(comp);
  }
  return [...comps];
}

const CATEGORY_SCOPES = NAV_RESOURCE_GROUPS.map((group) => ({
  id: `category:${group.id}`,
  label: group.label,
  kind: 'category',
  syncTypes: syncTypesForNavGroup(group.id),
  components: componentsForResourceIds(group.resourceIds),
}));

export const OPTIMIZATION_SYNC_SCOPES = [
  {
    id: 'all',
    label: 'All resources',
    kind: 'all',
    syncTypes: null,
    components: null,
  },
  ...CATEGORY_SCOPES,
  ...RESOURCE_SCOPES.map((s) => ({ ...s, kind: 'resource' })),
];

export const OPTIMIZATION_SCOPE_GROUPS = [
  { id: 'all', label: 'All' },
  { id: 'category', label: 'Categories' },
  { id: 'resource', label: 'Resource types' },
];

export function getOptimizationSyncScope(scopeId) {
  return OPTIMIZATION_SYNC_SCOPES.find((s) => s.id === scopeId) || OPTIMIZATION_SYNC_SCOPES[0];
}

export function isScopedOptimization(scopeId) {
  return Boolean(scopeId && scopeId !== 'all');
}

export function optimizationScopesByKind(kind) {
  return OPTIMIZATION_SYNC_SCOPES.filter((s) => s.kind === kind);
}

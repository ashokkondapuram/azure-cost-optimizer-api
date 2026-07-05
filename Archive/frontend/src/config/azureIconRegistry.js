/**
 * Open-source Azure icons via react-az-icons (ISC).
 * Deep imports keep the production bundle small (barrel import ships ~600 icons).
 */
import AzVirtualMachine from 'react-az-icons/dist/components/AzVirtualMachine';
import AzVMScaleSets from 'react-az-icons/dist/components/AzVMScaleSets';
import AzDisks from 'react-az-icons/dist/components/AzDisks';
import AzKubernetesServices from 'react-az-icons/dist/components/AzKubernetesServices';
import AzContainerRegistries from 'react-az-icons/dist/components/AzContainerRegistries';
import AzContainerInstances from 'react-az-icons/dist/components/AzContainerInstances';
import AzAppServices from 'react-az-icons/dist/components/AzAppServices';
import AzStorageAccounts from 'react-az-icons/dist/components/AzStorageAccounts';
import AzPublicIPAddresses from 'react-az-icons/dist/components/AzPublicIPAddresses';
import AzLoadBalancers from 'react-az-icons/dist/components/AzLoadBalancers';
import AzApplicationGateways from 'react-az-icons/dist/components/AzApplicationGateways';
import AzNetworkSecurityGroup from 'react-az-icons/dist/components/AzNetworkSecurityGroup';
import AzNAT from 'react-az-icons/dist/components/AzNAT';
import AzSQLServer from 'react-az-icons/dist/components/AzSQLServer';
import AzCosmosDB from 'react-az-icons/dist/components/AzCosmosDB';
import AzDatabasePostgreSQLServer from 'react-az-icons/dist/components/AzDatabasePostgreSQLServer';
import AzCacheRedis from 'react-az-icons/dist/components/AzCacheRedis';
import AzKeyVaults from 'react-az-icons/dist/components/AzKeyVaults';
import AzCostManagement from 'react-az-icons/dist/components/AzCostManagement';
import AzCostManagementandBilling from 'react-az-icons/dist/components/AzCostManagementandBilling';
import AzCostAnalysis from 'react-az-icons/dist/components/AzCostAnalysis';
import AzSubscriptions from 'react-az-icons/dist/components/AzSubscriptions';
import AzResourceGroups from 'react-az-icons/dist/components/AzResourceGroups';
import AzResourceGroupList from 'react-az-icons/dist/components/AzResourceGroupList';
import AzDashboard from 'react-az-icons/dist/components/AzDashboard';
import AzManagementPortal from 'react-az-icons/dist/components/AzManagementPortal';
import AzActivityLog from 'react-az-icons/dist/components/AzActivityLog';
import AzMonitor from 'react-az-icons/dist/components/AzMonitor';
import AzMonitorDashboard from 'react-az-icons/dist/components/AzMonitorDashboard';

/** Logical key → Azure icon component */
export const ICON_COMPONENTS = {
  virtualMachine: AzVirtualMachine,
  vmScaleSets: AzVMScaleSets,
  vmFleet: AzVMScaleSets,
  disks: AzDisks,
  kubernetes: AzKubernetesServices,
  aks: AzKubernetesServices,
  nodepool: AzVMScaleSets,
  k8sPod: AzContainerInstances,
  k8sNode: AzVirtualMachine,
  k8sNs: AzResourceGroupList,
  containerRegistry: AzContainerRegistries,
  container: AzContainerRegistries,
  appService: AzAppServices,
  storage: AzStorageAccounts,
  publicIp: AzPublicIPAddresses,
  loadBalancer: AzLoadBalancers,
  appGateway: AzApplicationGateways,
  nsg: AzNetworkSecurityGroup,
  nat: AzNAT,
  sql: AzSQLServer,
  cosmosdb: AzCosmosDB,
  postgresql: AzDatabasePostgreSQLServer,
  redis: AzCacheRedis,
  keyVault: AzKeyVaults,
  costManagement: AzCostManagement,
  costBilling: AzCostManagementandBilling,
  costAnalysis: AzCostAnalysis,
  subscription: AzSubscriptions,
  resourceGroup: AzResourceGroups,
  dashboard: AzDashboard,
  portal: AzManagementPortal,
  findings: AzCostAnalysis,
  history: AzActivityLog,
  engine: AzKubernetesServices,
  monitor: AzMonitor,
  monitorDashboard: AzMonitorDashboard,
  default: AzManagementPortal,
};

/** ARM resource type → logical key */
export const ARM_TYPE_KEYS = {
  'Microsoft.Compute/virtualMachines': 'virtualMachine',
  'Microsoft.Compute/virtualMachineScaleSets': 'vmScaleSets',
  'Microsoft.Compute/disks': 'disks',
  'Microsoft.ContainerService/managedClusters': 'aks',
  'Microsoft.ContainerInstance/containerGroups': 'k8sPod',
  'Microsoft.ContainerRegistry/registries': 'containerRegistry',
  'Microsoft.Storage/storageAccounts': 'storage',
  'Microsoft.Web/sites': 'appService',
  'Microsoft.Sql/servers': 'sql',
  'Microsoft.DBforPostgreSQL/flexibleServers': 'postgresql',
  'Microsoft.DocumentDB/databaseAccounts': 'cosmosdb',
  'Microsoft.Cache/redis': 'redis',
  'Microsoft.KeyVault/vaults': 'keyVault',
  'Microsoft.Network/publicIPAddresses': 'publicIp',
  'Microsoft.Network/loadBalancers': 'loadBalancer',
  'Microsoft.Network/applicationGateways': 'appGateway',
  'Microsoft.Network/networkSecurityGroups': 'nsg',
  'Microsoft.Network/natGateways': 'nat',
  'Microsoft.CostManagement/exports': 'costManagement',
};

export const CATEGORY_KEYS = {
  COMPUTE: 'virtualMachine',
  KUBERNETES: 'aks',
  STORAGE: 'storage',
  NETWORK: 'publicIp',
  DATABASE: 'sql',
  SECURITY: 'keyVault',
  COST: 'costManagement',
};

export const NAV_GROUP_KEYS = {
  compute: 'virtualMachine',
  containers: 'aks',
  appservices: 'appService',
  storage: 'storage',
  networking: 'publicIp',
  databases: 'sql',
  security: 'keyVault',
};

export const PAGE_ICON_KEYS = {
  dashboard: 'dashboard',
  costs: 'costManagement',
  findings: 'costAnalysis',
  engine: 'engine',
  history: 'history',
  subscription: 'subscription',
  resourceGroup: 'resourceGroup',
  vms: 'virtualMachine',
  vmFleet: 'vmFleet',
  disks: 'disks',
  aks: 'aks',
  acr: 'containerRegistry',
  appservices: 'appService',
  storage: 'storage',
  publicips: 'publicIp',
  loadbalancers: 'loadBalancer',
  appgateways: 'appGateway',
  nsgs: 'nsg',
  sql: 'sql',
  cosmosdb: 'cosmosdb',
  postgresql: 'postgresql',
  keyvaults: 'keyVault',
  kubernetes: 'kubernetes',
  nodepool: 'nodepool',
  k8sPod: 'k8sPod',
  k8sNode: 'k8sNode',
  k8sNs: 'k8sNs',
  logo: 'costBilling',
  settings: 'portal',
};

export const ROUTE_ICON_KEYS = {
  '/': 'dashboard',
  '/costs': 'costManagement',
  '/findings': 'costAnalysis',
  '/engine': 'engine',
  '/history': 'history',
  '/vms': 'virtualMachine',
  '/disks': 'disks',
  '/aks': 'aks',
  '/acr': 'containerRegistry',
  '/appservices': 'appService',
  '/storage': 'storage',
  '/publicips': 'publicIp',
  '/loadbalancers': 'loadBalancer',
  '/appgateways': 'appGateway',
  '/nsgs': 'nsg',
  '/sql': 'sql',
  '/cosmosdb': 'cosmosdb',
  '/postgresql': 'postgresql',
  '/keyvaults': 'keyVault',
  '/settings': 'portal',
};

export const API_PATH_KEYS = {
  '/resources/disks': 'disks',
  '/resources/acr': 'containerRegistry',
  '/resources/appservices': 'appService',
  '/resources/storage': 'storage',
  '/resources/publicips': 'publicIp',
  '/resources/loadbalancers': 'loadBalancer',
  '/resources/appgateways': 'appGateway',
  '/resources/nsgs': 'nsg',
  '/resources/sql': 'sql',
  '/resources/cosmosdb': 'cosmosdb',
  '/resources/postgresql': 'postgresql',
  '/resources/keyvaults': 'keyVault',
};

const COMPONENT_NAME_KEYS = {
  'Virtual Machines': 'virtualMachine',
  'Managed Disks': 'disks',
  'App Service': 'appService',
  'App Service Plans': 'appService',
  AKS: 'aks',
  'Storage Accounts': 'storage',
  'Public IPs': 'publicIp',
  'Load Balancers': 'loadBalancer',
  'Application Gateways': 'appGateway',
  'Network Security Groups': 'nsg',
  'NAT Gateways': 'nat',
  'Network Interfaces': 'publicIp',
  SQL: 'sql',
  'SQL Servers': 'sql',
  'Cosmos DB': 'cosmosdb',
  PostgreSQL: 'postgresql',
  Redis: 'redis',
  'Key Vaults': 'keyVault',
  'Container Registries': 'containerRegistry',
};

/** Legacy /icons/*.svg path → logical key (backward compat) */
const LEGACY_SRC_KEYS = {
  '/icons/azure/virtual-machine.svg': 'virtualMachine',
  '/icons/azure/virtual-machine-scale-set.svg': 'vmScaleSets',
  '/icons/azure/all-virtual-machines.svg': 'vmFleet',
  '/icons/azure/storage-cache.svg': 'storage',
  '/icons/azure/managed-clusters.svg': 'aks',
  '/icons/azure/container-group.svg': 'appService',
  '/icons/azure/global-view.svg': 'publicIp',
  '/icons/azure/cost-management.svg': 'costManagement',
  '/icons/azure/subscription.svg': 'subscription',
  '/icons/azure/resource-groups.svg': 'resourceGroup',
  '/icons/aks.svg': 'aks',
  '/icons/kubernetes.svg': 'kubernetes',
  '/icons/nodepool.svg': 'nodepool',
  '/icons/k8s-pod.svg': 'k8sPod',
  '/icons/k8s-node.svg': 'k8sNode',
  '/icons/k8s-ns.svg': 'k8sNs',
  '/icons/container.svg': 'containerRegistry',
  '/icons/virtual-machine.svg': 'virtualMachine',
};

export function getIconComponent(key) {
  if (!key) return ICON_COMPONENTS.default;
  return ICON_COMPONENTS[key] || ICON_COMPONENTS.default;
}

export function legacySrcToKey(src) {
  return LEGACY_SRC_KEYS[src] || null;
}

export function iconKeyForAzureType(type) {
  if (!type) return null;
  if (ARM_TYPE_KEYS[type]) return ARM_TYPE_KEYS[type];
  if (type.includes('virtualMachines')) return 'virtualMachine';
  if (type.includes('virtualMachineScaleSets')) return 'vmScaleSets';
  if (type.includes('managedClusters') || type.includes('ContainerService')) return 'aks';
  if (type.includes('ContainerRegistry')) return 'containerRegistry';
  if (type.includes('ContainerInstance')) return 'k8sPod';
  if (type.includes('Storage')) return 'storage';
  if (type.includes('Network/publicIP')) return 'publicIp';
  if (type.includes('loadBalancers')) return 'loadBalancer';
  if (type.includes('applicationGateways')) return 'appGateway';
  if (type.includes('networkSecurityGroups')) return 'nsg';
  if (type.includes('natGateways')) return 'nat';
  if (type.includes('Network')) return 'publicIp';
  if (type.includes('PostgreSQL')) return 'postgresql';
  if (type.includes('DocumentDB') || type.includes('Cosmos')) return 'cosmosdb';
  if (type.includes('Sql')) return 'sql';
  if (type.includes('redis') || type.includes('Redis')) return 'redis';
  if (type.includes('KeyVault')) return 'keyVault';
  if (type.includes('Web')) return 'appService';
  if (type.includes('CostManagement')) return 'costManagement';
  return 'default';
}

export function iconKeyForCategory(category) {
  return CATEGORY_KEYS[(category || '').toUpperCase()] || null;
}

export function iconKeyForComponent(component) {
  if (!component) return null;
  if (COMPONENT_NAME_KEYS[component]) return COMPONENT_NAME_KEYS[component];
  const lower = component.toLowerCase();
  if (lower.includes('vm') || lower.includes('virtual')) return 'virtualMachine';
  if (lower.includes('disk')) return 'disks';
  if (lower.includes('aks') || lower.includes('kubernetes')) return 'aks';
  if (lower.includes('storage')) return 'storage';
  if (lower.includes('gateway')) return 'appGateway';
  if (lower.includes('load balancer')) return 'loadBalancer';
  if (lower.includes('network') || lower.includes('ip') || lower.includes('nic')) return 'publicIp';
  if (lower.includes('cosmos')) return 'cosmosdb';
  if (lower.includes('postgres')) return 'postgresql';
  if (lower.includes('sql') || lower.includes('database')) return 'sql';
  if (lower.includes('redis')) return 'redis';
  if (lower.includes('key vault')) return 'keyVault';
  if (lower.includes('app service')) return 'appService';
  if (lower.includes('container registr')) return 'containerRegistry';
  if (lower.includes('nat')) return 'nat';
  return 'default';
}

export function iconKeyForRoute(pathname) {
  return ROUTE_ICON_KEYS[pathname] || 'dashboard';
}

export function iconKeyForApiPath(apiPath) {
  return API_PATH_KEYS[apiPath] || null;
}

export function iconKeyFromResourceId(resourceId) {
  if (!resourceId) return null;
  const match = resourceId.match(/\/providers\/(.+?)\/[^/]+$/i);
  return match ? iconKeyForAzureType(match[1]) : null;
}

export function resolveIconKey({
  iconKey,
  src,
  armType,
  category,
  component,
  route,
  apiPath,
  resourceId,
} = {}) {
  return (
    iconKey
    || (src && !src.startsWith('/') ? src : null)
    || legacySrcToKey(src)
    || iconKeyFromResourceId(resourceId)
    || iconKeyForAzureType(armType)
    || iconKeyForCategory(category)
    || iconKeyForComponent(component)
    || (route != null ? iconKeyForRoute(route) : null)
    || iconKeyForApiPath(apiPath)
    || null
  );
}

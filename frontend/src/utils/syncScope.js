/** Map list API paths to canonical sync types (mirrors app/sync_scope.py). */

import { PER_TYPE_API_PATH_TO_CANONICAL } from '../config/resourcePageCatalog';

const API_PATH_TO_TYPE = {
  '/resources/vms': 'compute/vm',
  '/resources/vmss': 'compute/vmss',
  '/resources/disks': 'compute/disk',
  '/resources/snapshots': 'compute/snapshot',
  '/resources/aks': 'containers/aks',
  '/resources/acr': 'containers/acr',
  '/resources/storage': 'storage/account',
  '/resources/publicips': 'network/publicip',
  '/resources/vnets': 'network/vnet',
  '/resources/nics': 'network/nic',
  '/resources/natgateways': 'network/nat',
  '/resources/loadbalancers': 'network/loadbalancer',
  '/resources/appgateways': 'network/appgateway',
  '/resources/nsgs': 'network/nsg',
  '/resources/privateendpoints': 'network/privateendpoint',
  '/resources/privatelinkservices': 'network/privatelinkservice',
  '/resources/privatedns': 'network/privatedns',
  '/resources/sql': 'database/sql',
  '/resources/cosmosdb': 'database/cosmosdb',
  '/resources/postgresql': 'database/postgresql',
  '/resources/redis': 'database/redis',
  '/resources/appservices': 'appservice/webapp',
  '/resources/appserviceplans': 'appservice/plan',
  '/resources/keyvaults': 'security/keyvault',
  ...PER_TYPE_API_PATH_TO_CANONICAL,
};

/** @deprecated Legacy aggregate paths — still resolve for scoped sync. */
const LEGACY_AGGREGATE_API_PATH_TO_TYPES = {
  '/resources/monitoring': [
    'monitoring/loganalytics',
    'monitoring/appinsights',
  ],
  '/resources/integration': [
    'integration/apim',
    'integration/datafactory',
    'integration/logicapp',
  ],
  '/resources/messaging': [
    'messaging/eventhub',
    'messaging/servicebus',
  ],
  '/resources/analytics': [
    'analytics/databricks',
    'analytics/synapse',
    'analytics/adx',
    'analytics/mlworkspace',
  ],
  '/resources/backup': ['backup/recoveryvault'],
  '/resources/search': ['search/cognitivesearch'],
};

export const DEFAULT_RESOURCE_PAGE_SIZE = 50;

/** List pages that need properties_json for display (address space, pools, etc.). */
export const API_PATHS_NEEDING_PROPERTIES = new Set([
  '/resources/aks',
  '/resources/vnets',
  '/resources/appgateways',
  '/resources/privateendpoints',
  '/resources/privatelinkservices',
  '/resources/privatedns',
  '/resources/appservices',
  '/resources/appserviceplans',
]);

export function apiPathNeedsProperties(apiPath) {
  return API_PATHS_NEEDING_PROPERTIES.has(String(apiPath || '').trim().toLowerCase().replace(/\/+$/, ''));
}

export function syncTypesForApiPath(apiPath) {
  const path = String(apiPath || '').trim().toLowerCase().replace(/\/+$/, '');
  if (LEGACY_AGGREGATE_API_PATH_TO_TYPES[path]) {
    return [...LEGACY_AGGREGATE_API_PATH_TO_TYPES[path]];
  }
  const canonical = API_PATH_TO_TYPE[path];
  return canonical ? [canonical] : [];
}

export function isPaginatedResponse(data) {
  return data != null && Array.isArray(data.items) && typeof data.total === 'number';
}

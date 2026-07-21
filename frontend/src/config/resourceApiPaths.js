/**
 * Canonical resource API paths — mirrors app/resource_api_paths.py.
 * Primary list path: /resources/{canonical_type} (e.g. /resources/compute/disk).
 */

import { PER_TYPE_API_PATH_TO_CANONICAL } from './resourcePageCatalog';

export function canonicalApiPath(canonicalType) {
  const ct = String(canonicalType || '').trim().toLowerCase();
  return `/resources/${ct}`;
}

/** Count key → canonical type (core inventory pages). */
export const COUNT_KEY_TO_CANONICAL = {
  vms: 'compute/vm',
  disks: 'compute/disk',
  snapshots: 'compute/snapshot',
  aks: 'containers/aks',
  acr: 'containers/acr',
  storage: 'storage/account',
  publicips: 'network/publicip',
  vnets: 'network/vnet',
  nics: 'network/nic',
  natgateways: 'network/nat',
  loadbalancers: 'network/loadbalancer',
  appgateways: 'network/appgateway',
  nsgs: 'network/nsg',
  privateendpoints: 'network/privateendpoint',
  privatelinkservices: 'network/privatelinkservice',
  privatedns: 'network/privatedns',
  sql: 'database/sql',
  cosmosdb: 'database/cosmosdb',
  postgresql: 'database/postgresql',
  redis: 'database/redis',
  appservices: 'appservice/webapp',
  appserviceplans: 'appservice/plan',
  keyvaults: 'security/keyvault',
  ...Object.fromEntries(
    Object.entries(PER_TYPE_API_PATH_TO_CANONICAL).map(([path, ct]) => [
      path.replace('/resources/', ''),
      ct,
    ]),
  ),
};

/** Legacy slug path → canonical type (includes canonical paths). */
export const API_PATH_TO_CANONICAL = (() => {
  const out = {};
  for (const [key, ct] of Object.entries(COUNT_KEY_TO_CANONICAL)) {
    out[`/resources/${key}`] = ct;
    out[canonicalApiPath(ct)] = ct;
  }
  return out;
})();

/** Canonical type → primary API list path. */
export const CANONICAL_TO_API_PATH = Object.fromEntries(
  Object.values(COUNT_KEY_TO_CANONICAL).map((ct) => [ct, canonicalApiPath(ct)]),
);

export function apiPathForCanonical(canonicalType) {
  const ct = String(canonicalType || '').trim().toLowerCase();
  return CANONICAL_TO_API_PATH[ct] || canonicalApiPath(ct);
}

export function apiPathForCountKey(countKey) {
  const key = String(countKey || '').trim().toLowerCase();
  const ct = COUNT_KEY_TO_CANONICAL[key];
  return ct ? apiPathForCanonical(ct) : null;
}

export function canonicalFromApiPath(apiPath) {
  const path = String(apiPath || '').trim().toLowerCase().replace(/\/+$/, '');
  return API_PATH_TO_CANONICAL[path] || null;
}

/** @deprecated Legacy aggregate list paths — resolve for scoped sync only. */
export const LEGACY_AGGREGATE_API_PATH_TO_TYPES = {
  '/resources/monitoring': ['monitoring/loganalytics', 'monitoring/appinsights'],
  '/resources/integration': ['integration/apim', 'integration/datafactory', 'integration/logicapp'],
  '/resources/messaging': ['messaging/eventhub', 'messaging/servicebus'],
  '/resources/analytics': [
    'analytics/databricks',
    'analytics/synapse',
    'analytics/adx',
    'analytics/mlworkspace',
  ],
  '/resources/backup': ['backup/recoveryvault'],
  '/resources/search': ['search/cognitivesearch'],
};

export function syncTypesForCanonicalApiPath(apiPath) {
  const path = String(apiPath || '').trim().toLowerCase().replace(/\/+$/, '');
  if (LEGACY_AGGREGATE_API_PATH_TO_TYPES[path]) {
    return [...LEGACY_AGGREGATE_API_PATH_TO_TYPES[path]];
  }
  const ct = canonicalFromApiPath(path);
  return ct ? [ct] : [];
}

/** Nested resource routes under canonical prefixes. */
export const CANONICAL_NESTED_PATHS = {
  vmSizing: (resourceGroup, vmName) =>
    `/resources/compute/vm/${encodeURIComponent(resourceGroup)}/${encodeURIComponent(vmName)}/sizing`,
  vmSizingOpenFinding: (resourceGroup, vmName) =>
    `/resources/compute/vm/${encodeURIComponent(resourceGroup)}/${encodeURIComponent(vmName)}/sizing/open-finding`,
  aksKubernetesVersions: '/resources/containers/aks/kubernetes-versions',
  aksPoolInstances: '/resources/containers/aks/pool-instances',
};

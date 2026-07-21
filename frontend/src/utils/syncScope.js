/** Map list API paths to canonical sync types (mirrors app/sync_scope.py). */

import {
  LEGACY_AGGREGATE_API_PATH_TO_TYPES,
  syncTypesForCanonicalApiPath,
} from '../config/resourceApiPaths';

export { COUNT_KEY_TO_CANONICAL } from '../config/resourceApiPaths';

export const DEFAULT_RESOURCE_PAGE_SIZE = 50;

/** List pages that need properties_json for display (address space, pools, etc.). */
export const API_PATHS_NEEDING_PROPERTIES = new Set([
  '/resources/containers/aks',
  '/resources/network/vnet',
  '/resources/network/appgateway',
  '/resources/network/privateendpoint',
  '/resources/network/privatelinkservice',
  '/resources/network/privatedns',
  '/resources/appservice/webapp',
  '/resources/appservice/plan',
]);

export function apiPathNeedsProperties(apiPath) {
  const path = String(apiPath || '').trim().toLowerCase().replace(/\/+$/, '');
  if (API_PATHS_NEEDING_PROPERTIES.has(path)) return true;
  // Legacy slug paths still accepted during transition.
  const legacy = {
    '/resources/aks': true,
    '/resources/vnets': true,
    '/resources/appgateways': true,
    '/resources/privateendpoints': true,
    '/resources/privatelinkservices': true,
    '/resources/privatedns': true,
    '/resources/appservices': true,
    '/resources/appserviceplans': true,
  };
  return Boolean(legacy[path]);
}

export function syncTypesForApiPath(apiPath) {
  const path = String(apiPath || '').trim().toLowerCase().replace(/\/+$/, '');
  if (LEGACY_AGGREGATE_API_PATH_TO_TYPES[path]) {
    return [...LEGACY_AGGREGATE_API_PATH_TO_TYPES[path]];
  }
  return syncTypesForCanonicalApiPath(path);
}

export function isPaginatedResponse(data) {
  return data != null && Array.isArray(data.items) && typeof data.total === 'number';
}

import DiskPropertiesPanel from '../components/DiskPropertiesPanel';
import { apiPathForCanonical } from '../../../config/resourceApiPaths';
import { isDiskResource } from '../utils/diskUtils';

export const SERVICE_ID = 'compute-disk';
export const CANONICAL_TYPE = 'compute/disk';
export const API_PATH = apiPathForCanonical(CANONICAL_TYPE);

export function matchesResource(resource, apiPath = '') {
  return isDiskResource(resource, apiPath);
}

export { DiskPropertiesPanel as PropertiesPanel };

export function enrichInventoryContext(base, resource, apiPath = '') {
  if (!matchesResource(resource, apiPath)) return base;
  return {
    ...base,
    canonicalType: CANONICAL_TYPE,
    diskPropertiesShown: true,
  };
}

export function hideStateKpi(resource, apiPath = '') {
  return matchesResource(resource, apiPath);
}

export function skipOverviewTiles(resource, apiPath = '') {
  return matchesResource(resource, apiPath);
}

export function collapseMetricsSection(resource, apiPath = '') {
  return matchesResource(resource, apiPath);
}

export function costDriversDefaultOpen({ resource, apiPath, findingsCount = 0, triggerCount = 0 }) {
  if (matchesResource(resource, apiPath)) return false;
  return findingsCount > 0 || triggerCount > 0;
}

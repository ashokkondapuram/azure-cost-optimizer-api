import { matchesResource, CANONICAL_TYPE } from '../index';
import { normalizeAksCluster, resolveNodeAutoProvisioningLabel } from '../utils/aksNormalize';
import { aggregatePoolUtilization, attachPoolInstances } from '../utils/aksPoolUtilization';

export function enrichDrawerResource(resource, {
  apiPath = '',
  metricsData = null,
} = {}) {
  if (!matchesResource(resource, apiPath)) return resource;

  const normalized = normalizeAksCluster(resource);
  const nodeAutoProvisioning = resolveNodeAutoProvisioningLabel(resource, metricsData);
  const clusterName = normalized.name || '';
  const facts = metricsData?.facts || {};
  const instances = metricsData?.instances || [];
  const poolMetrics = metricsData?.pool_metrics || [];
  const poolsWithUtil = aggregatePoolUtilization(
    clusterName,
    normalized._pools,
    instances,
    facts,
    poolMetrics,
  );
  const pools = attachPoolInstances(poolsWithUtil, poolMetrics);

  return {
    ...normalized,
    _nodeAutoProvisioning: nodeAutoProvisioning,
    _nodeAutoProvisioningEnabled: nodeAutoProvisioning === 'Enabled',
    _pools: pools,
  };
}

export function enrichInventoryContext(base, resource, apiPath = '') {
  if (!matchesResource(resource, apiPath)) return base;
  return {
    ...base,
    canonicalType: CANONICAL_TYPE,
    aksPoolsShown: (resource?._pools?.length || 0) > 0,
  };
}

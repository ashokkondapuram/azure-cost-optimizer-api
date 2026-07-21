import {
  buildApplicationGatewaySummaryRows,
  isApplicationGatewayResource,
} from './applicationGatewayPropertySummary';
import { trendMetricKeysForType } from './drawerTrendMetrics';
import { matchesResource as matchesAksResource } from '../it-services/containers-aks';
import { normalizeAksCluster, normalizeAksPools, resolveNodeAutoProvisioningLabel } from '../it-services/containers-aks/utils/aksNormalize';
import { essentialsRowMatchKey } from './drawerOverviewDedupe';

function arrayCount(value) {
  return Array.isArray(value) ? value.length : null;
}

function countFromPayload(metricsData, factKey) {
  if (!metricsData) return null;
  const key = String(factKey || '').toLowerCase();
  const rows = [
    ...(metricsData.metrics || []),
    ...(metricsData.derived || []),
    ...(metricsData.inventory_properties || []),
  ];
  const row = rows.find((entry) => String(entry?.fact_key || '').toLowerCase() === key);
  if (row?.value != null) {
    const num = Number(row.value);
    if (Number.isFinite(num)) return num;
  }
  const facts = metricsData.facts || {};
  if (facts[factKey] != null) {
    const num = Number(facts[factKey]);
    if (Number.isFinite(num)) return num;
  }
  return null;
}

/** True when the drawer should show property counts instead of CPU/memory metrics. */
export function isApplicationGateway(canonicalType = '', armType = '') {
  const key = String(canonicalType || armType || '').toLowerCase();
  return key.includes('network/appgateway')
    || key.includes('microsoft.network/applicationgateways');
}

export { isApplicationGatewayResource } from './applicationGatewayPropertySummary';

/** Hide Azure Monitor CPU/memory tab for application gateways. */
export function shouldHideGenericMetrics(canonicalType = '', armType = '') {
  return isApplicationGateway(canonicalType, armType);
}

/** Drawer trend / summary metric specs for a resource type. */
export function drawerPropertyMetricSpecs(canonicalType = '', armType = '') {
  const specs = trendMetricKeysForType(canonicalType, armType);
  return specs.some((spec) => spec.static) ? specs : null;
}

/** Extract backend pool and health probe counts from synced properties or inventory. */
export function applicationGatewayCounts(resource, metricsData = null) {
  const props = resource?.properties || {};

  const backendPools = countFromPayload(metricsData, 'backend_pool_count')
    ?? arrayCount(props.backendAddressPools);
  const healthProbes = countFromPayload(metricsData, 'health_probe_count')
    ?? arrayCount(props.probes)
    ?? arrayCount(props.healthProbes);

  if (backendPools == null && healthProbes == null) return null;

  return {
    backend_pool_count: backendPools ?? 0,
    health_probe_count: healthProbes ?? 0,
  };
}

/** Summary cards for property-backed drawer metrics (e.g. application gateway pools/probes). */
export function drawerStaticMetricCards(resource, metricSpecs = [], metricsData = null, {
  canonicalType = '',
  armType = '',
} = {}) {
  if (!metricSpecs.some((spec) => spec.static)) return [];

  const counts = isApplicationGateway(canonicalType, armType)
    ? applicationGatewayCounts(resource, metricsData)
    : null;
  if (!counts) return [];

  return metricSpecs
    .filter((spec) => spec.static)
    .map((spec) => {
      const raw = counts[spec.factKey];
      if (raw == null) return null;
      return {
        label: spec.label,
        value: String(raw),
        detail: spec.unit ? `${raw} ${spec.unit}` : null,
      };
    })
    .filter(Boolean);
}

function pushUniqueEssentialRow(rows, seenLabels, presentKeys, row) {
  if (!row?.label) return;
  const matchKey = essentialsRowMatchKey(row);
  if (matchKey && presentKeys.has(matchKey)) return;
  if (seenLabels.has(row.label)) return;
  rows.push(row);
  seenLabels.add(row.label);
  if (matchKey) presentKeys.add(matchKey);
}

/** Add application-gateway essentials rows (backend pools and health probes). */
export function enrichDrawerEssentials(
  rows,
  resource,
  seenLabels = new Set(),
  apiPath = '',
  metricsData = null,
  { skipPoolSummary = false } = {},
) {
  const presentKeys = new Set(rows.map((row) => essentialsRowMatchKey(row)).filter(Boolean));

  if (isApplicationGatewayResource(resource, apiPath)) {
    for (const row of buildApplicationGatewaySummaryRows(resource?.properties)) {
      pushUniqueEssentialRow(rows, seenLabels, presentKeys, row);
    }
  }

  if (matchesAksResource(resource, apiPath)) {
    const normalized = resource?._nodeAutoProvisioning != null
      ? resource
      : normalizeAksCluster(resource);
    const pools = normalized?._pools?.length
      ? normalized._pools
      : normalizeAksPools(resource);

    if (!skipPoolSummary && pools.length) {
      pushUniqueEssentialRow(rows, seenLabels, presentKeys, {
        key: 'pool_count',
        fact_key: 'pool_count',
        label: 'Node pools',
        value: String(pools.length),
      });
    }

    const nodeCount = normalized?._nodeCount
      ?? pools.reduce((sum, pool) => sum + (pool.count || 0), 0);
    if (nodeCount > 0) {
      pushUniqueEssentialRow(rows, seenLabels, presentKeys, {
        key: 'node_count',
        fact_key: 'node_count',
        label: 'Nodes',
        value: String(nodeCount),
      });
    }

    const napValue = resolveNodeAutoProvisioningLabel(resource, metricsData);
    pushUniqueEssentialRow(rows, seenLabels, presentKeys, {
      key: 'node_auto_provisioning',
      fact_key: 'node_auto_provisioning',
      label: 'Node auto provisioning',
      value: napValue,
    });
  }

  return rows;
}

/** True when property-backed drawer metrics are available for Trends. */
export function hasDrawerPropertyMetrics(resource, metricsData = null, canonicalType = '', armType = '') {
  const specs = drawerPropertyMetricSpecs(canonicalType, armType);
  if (!specs?.length) return false;
  return drawerStaticMetricCards(resource, specs, metricsData, { canonicalType, armType }).length > 0;
}

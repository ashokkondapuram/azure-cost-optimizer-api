/** Normalize AKS cluster records from DB snapshots or live ARM responses. */

import { formatPowerState, toDisplayText } from '../../../utils/formatDisplay';

function extractResourceGroup(cluster) {
  if (cluster?.resourceGroup) return cluster.resourceGroup;
  if (cluster?.resource_group) return cluster.resource_group;
  const parts = (cluster?.id || '').split('/');
  const rgIdx = parts.findIndex((part) => part.toLowerCase() === 'resourcegroups');
  return rgIdx >= 0 ? parts[rgIdx + 1] : '';
}

function normalizePool(pool) {
  if (!pool) return null;
  if (pool.count != null || pool.vmSize) {
    return {
      name: pool.name,
      count: pool.count ?? 0,
      vmSize: pool.vmSize,
      mode: pool.mode,
      osType: pool.osType,
    };
  }
  const props = pool.properties || {};
  return {
    name: pool.name,
    count: props.count ?? 0,
    vmSize: props.vmSize,
    mode: props.mode,
    osType: props.osType,
  };
}

export function normalizeAksPools(cluster) {
  const props = cluster?.properties || {};
  const raw = props.agentPoolProfiles || cluster?.agentPoolProfiles || [];
  return raw.map(normalizePool).filter(Boolean);
}

function formatAksNetwork(networkProfile) {
  if (!networkProfile || typeof networkProfile !== 'object') return '';
  const plugin = networkProfile.networkPlugin || networkProfile.network_plugin;
  const policy = networkProfile.networkPolicy || networkProfile.network_policy;
  if (plugin && policy && policy !== plugin) return `${plugin} (${policy})`;
  return plugin || policy || '';
}

export function normalizeAksCluster(cluster) {
  const p = cluster?.properties || {};
  const pools = normalizeAksPools(cluster);
  const nodeCount = pools.reduce((sum, pool) => sum + (pool.count || 0), 0);
  const rawState = p.powerState ?? cluster?.state ?? p.provisioningState ?? cluster?.status;
  const state = formatPowerState(rawState);
  const sku = toDisplayText(
    (typeof cluster?.sku === 'string' && cluster.sku)
      ? cluster.sku
      : (cluster?.sku ?? p.sku),
  );
  const networkProfile = p.networkProfile || cluster?.networkProfile || {};
  const network = toDisplayText(
    formatAksNetwork(networkProfile)
      || cluster?.network
      || cluster?.network_plugin,
  );
  const version = toDisplayText(
    p.kubernetesVersion
      || p.currentKubernetesVersion
      || cluster?.kubernetesVersion
      || cluster?.kubernetes_version,
  );
  const resourceGroup = extractResourceGroup(cluster);

  return {
    ...cluster,
    resourceGroup,
    _pools: pools,
    _nodeCount: nodeCount,
    _state: state,
    _version: version === '—' ? '—' : version,
    _sku: sku,
    _network: network,
  };
}

function clusterDedupeKey(cluster) {
  const name = (cluster?.name || '').trim().toLowerCase();
  if (name) return `name:${name}`;
  const id = (cluster?.id || '').trim().toLowerCase();
  if (id) return `id:${id}`;
  const rg = extractResourceGroup(cluster).toLowerCase();
  return rg ? `rg:${rg}|${name}` : '';
}

function clusterRichness(cluster) {
  const normalized = normalizeAksCluster(cluster);
  return (
    normalized._pools.length * 100
    + normalized._nodeCount
    + (normalized._state !== 'Unknown' ? 10 : 0)
    + (normalized._sku !== '—' ? 5 : 0)
    + (normalized.syncedAt ? 1 : 0)
  );
}

export function dedupeAksClusters(clusters) {
  const byKey = new Map();
  for (const cluster of clusters || []) {
    const key = clusterDedupeKey(cluster);
    if (!key) continue;
    const existing = byKey.get(key);
    if (!existing || clusterRichness(cluster) > clusterRichness(existing)) {
      byKey.set(key, cluster);
    }
  }
  return [...byKey.values()];
}

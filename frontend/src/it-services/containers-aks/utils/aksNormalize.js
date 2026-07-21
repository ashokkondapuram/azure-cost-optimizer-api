/** Normalize AKS cluster records from DB snapshots or live ARM responses. */

import { formatPowerState, toDisplayText } from '../../../utils/formatDisplay';
import { resolvePoolVmssRef } from './aksVmssMatch';

function extractResourceGroup(cluster) {
  if (cluster?.resourceGroup) return cluster.resourceGroup;
  if (cluster?.resource_group) return cluster.resource_group;
  const parts = (cluster?.id || '').split('/');
  const rgIdx = parts.findIndex((part) => part.toLowerCase() === 'resourcegroups');
  return rgIdx >= 0 ? parts[rgIdx + 1] : '';
}

function formatAutoscaleRange(enableAutoScaling, minCount, maxCount, count) {
  if (enableAutoScaling && minCount != null && maxCount != null) {
    return `${minCount} – ${maxCount}`;
  }
  if (enableAutoScaling && minCount != null) {
    return `≥ ${minCount}`;
  }
  if (count != null) return String(count);
  return '—';
}

function normalizePool(pool, vmssByPool = {}) {
  if (!pool) return null;
  const props = pool.properties || {};
  const count = pool.count ?? props.count ?? 0;
  const vmSize = pool.vmSize ?? props.vmSize;
  const osType = pool.osType ?? props.osType;
  const enableAutoScaling = pool.enableAutoScaling ?? props.enableAutoScaling ?? false;
  const minCount = pool.minCount ?? props.minCount ?? props.autoScalerProfile?.minCount;
  const maxCount = pool.maxCount ?? props.maxCount ?? props.autoScalerProfile?.maxCount;
  const vmss = resolvePoolVmssRef(pool, vmssByPool);
  const napMode = pool.nodeProvisioningMode ?? props.nodeProvisioningMode;
  const mode = pool.mode ?? props.mode;
  const displayMode = pool._napPool || String(napMode || '').toLowerCase() === 'auto'
    ? 'Auto provisioning'
    : mode;

  if (!pool.name && count == null && !vmSize) return null;

  return {
    name: pool.name,
    count,
    vmSize,
    mode: displayMode,
    osType,
    enableAutoScaling: Boolean(enableAutoScaling),
    minCount: minCount ?? null,
    maxCount: maxCount ?? null,
    autoscaleRange: formatAutoscaleRange(enableAutoScaling, minCount, maxCount, count),
    vmssId: vmss.vmssId,
    vmssName: vmss.vmssName,
    vmssSource: vmss.vmssSource,
    _vmssId: vmss.vmssId,
    _vmssName: vmss.vmssName,
    _napPool: Boolean(pool._napPool || String(napMode || '').toLowerCase() === 'auto'),
    vmssInstances: pool.vmssInstances || props.vmssInstances || [],
  };
}

export function normalizeAksPools(cluster) {
  const props = cluster?.properties || {};
  const vmssByPool = props._vmssByPool || cluster?._vmssByPool || {};
  const raw = props.agentPoolProfiles || cluster?.agentPoolProfiles || [];
  return raw.map((pool) => normalizePool(pool, vmssByPool)).filter(Boolean);
}

function formatAksNetwork(networkProfile) {
  if (!networkProfile || typeof networkProfile !== 'object') return '';
  const plugin = networkProfile.networkPlugin || networkProfile.network_plugin;
  const policy = networkProfile.networkPolicy || networkProfile.network_policy;
  if (plugin && policy && policy !== plugin) return `${plugin} (${policy})`;
  return plugin || policy || '';
}

function nodeAutoProvisioningLabel(nodeProvisioningProfile) {
  const mode = nodeProvisioningProfile?.mode ?? nodeProvisioningProfile?.Mode;
  return String(mode || '').trim().toLowerCase() === 'auto' ? 'Enabled' : 'Disabled';
}

function napLabelFromInventory(metricsData) {
  const row = (metricsData?.inventory_properties || []).find(
    (entry) => String(entry?.fact_key || '').toLowerCase() === 'node_auto_provisioning',
  );
  if (!row?.value) return null;
  const val = String(row.value).trim();
  if (/^enabled$/i.test(val) || val.toLowerCase() === 'auto') return 'Enabled';
  if (/^disabled$/i.test(val) || val.toLowerCase() === 'manual') return 'Disabled';
  return val;
}

/** Resolve NAP display label from synced properties or drawer metrics inventory. */
export function resolveNodeAutoProvisioningLabel(resource, metricsData = null) {
  const normalized = normalizeAksCluster(resource);
  return napLabelFromInventory(metricsData) || normalized._nodeAutoProvisioning || 'Disabled';
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
  const napProfile = p.nodeProvisioningProfile || cluster?.nodeProvisioningProfile;
  const nodeAutoProvisioning = nodeAutoProvisioningLabel(napProfile);
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
    _nodeResourceGroup: p.nodeResourceGroup || cluster?.nodeResourceGroup || '',
    _state: state,
    _version: version === '—' ? '—' : version,
    _sku: sku,
    _network: network,
    _nodeAutoProvisioning: nodeAutoProvisioning,
    _nodeAutoProvisioningEnabled: nodeAutoProvisioning === 'Enabled',
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

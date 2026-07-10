/** Disk helpers — owned by compute-disk IT service (frontend). */

import { formatPowerState, toDisplayText } from '../../../utils/formatDisplay';
import { formatDateTime } from '../../../utils/format';
import {
  parseComputeHostAttachment,
  shortArmResourceLabel,
} from '../../../utils/armResourceLinks';
import {
  formatMetricStatValue,
  labelForFactKey,
  normalizeMetricRow,
} from '../../../utils/resourceMetricsUtils';
import { metricTimespanLabel } from '../../../utils/metricsTimespanUtils';
import { resolveDiskProvisionedPerformance } from './diskProvisionedLimits';

const DISK_ARM_PROPERTY_ALIASES = {
  diskSizeGB: ['diskSizeGB', 'DiskSizeGB'],
  diskState: ['diskState', 'DiskState'],
  diskIOPSReadWrite: ['diskIOPSReadWrite', 'DiskIOPSReadWrite'],
  diskMBpsReadWrite: ['diskMBpsReadWrite', 'DiskMBpsReadWrite'],
  managedBy: ['managedBy', 'ManagedBy'],
  managedByExtended: ['managedByExtended', 'ManagedByExtended'],
  lastManagedBy: ['lastManagedBy', 'LastManagedBy'],
  shareInfo: ['shareInfo', 'ShareInfo'],
  timeCreated: ['timeCreated', 'TimeCreated'],
  lastOwnershipUpdateTime: ['lastOwnershipUpdateTime', 'LastOwnershipUpdateTime'],
  provisioningState: ['provisioningState', 'ProvisioningState', 'provisioning_state'],
  tier: ['tier', 'Tier'],
  burstingEnabled: ['burstingEnabled', 'BurstingEnabled'],
};

const DISK_USAGE_FACT_KEYS = [
  'disk_read_bps',
  'disk_write_bps',
  'disk_read_iops',
  'disk_write_iops',
  'disk_paid_burst_iops',
  'disk_iops_utilization_pct',
  'disk_throughput_utilization_pct',
];

export function isDiskResource(resource, apiPath = '') {
  const type = (resource?.type || '').toLowerCase();
  if (type.includes('disk') && !type.includes('snapshot')) return true;
  return String(apiPath || '').includes('/disks');
}

export function diskPropertyValue(props, canonicalKey) {
  if (!props || typeof props !== 'object') return undefined;
  const aliases = DISK_ARM_PROPERTY_ALIASES[canonicalKey] || [canonicalKey];
  for (const key of aliases) {
    const value = props[key];
    if (value != null && value !== '') return value;
  }
  return undefined;
}

export function normalizeDiskProperties(resource, metricsData = null) {
  const raw = resource?.properties || {};
  const normalized = { ...raw };
  for (const canonicalKey of Object.keys(DISK_ARM_PROPERTY_ALIASES)) {
    const value = diskPropertyValue(raw, canonicalKey);
    if (value != null && value !== '') normalized[canonicalKey] = value;
  }

  const facts = resource?._technical_facts;
  if (facts && typeof facts === 'object') {
    if (normalized.diskIOPSReadWrite == null && facts.provisioned_iops != null) {
      normalized.diskIOPSReadWrite = facts.provisioned_iops;
    }
    if (normalized.diskMBpsReadWrite == null && facts.provisioned_mbps != null) {
      normalized.diskMBpsReadWrite = facts.provisioned_mbps;
    }
    if (normalized.diskSizeGB == null && facts.size_gb != null) {
      normalized.diskSizeGB = facts.size_gb;
    }
  }

  for (const row of metricsData?.inventory_properties || []) {
    const key = row?.fact_key;
    const value = row?.value;
    if (value == null || value === '') continue;
    if (key === 'provisioned_iops' && normalized.diskIOPSReadWrite == null) {
      normalized.diskIOPSReadWrite = value;
    }
    if (key === 'provisioned_mbps' && normalized.diskMBpsReadWrite == null) {
      normalized.diskMBpsReadWrite = value;
    }
    if (key === 'size_gb' && normalized.diskSizeGB == null) {
      normalized.diskSizeGB = value;
    }
  }

  if (normalized.diskIOPSReadWrite == null || normalized.diskMBpsReadWrite == null) {
    const resolved = resolveDiskProvisionedPerformance({
      properties: normalized,
      sku: resource?.sku || (normalized.sku ? { name: normalized.sku } : null),
    });
    if (normalized.diskIOPSReadWrite == null && resolved.iops != null) {
      normalized.diskIOPSReadWrite = resolved.iops;
    }
    if (normalized.diskMBpsReadWrite == null && resolved.mbps != null) {
      normalized.diskMBpsReadWrite = resolved.mbps;
    }
  }

  return normalized;
}

function formatProvisionedCount(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return toDisplayText(value);
  return num.toLocaleString();
}

export function diskProvisionedIops(resource, metricsData = null) {
  const props = normalizeDiskProperties(resource, metricsData);
  const value = props.diskIOPSReadWrite;
  if (value == null || value === '') return null;
  return value;
}

export function diskProvisionedMbps(resource, metricsData = null) {
  const props = normalizeDiskProperties(resource, metricsData);
  const value = props.diskMBpsReadWrite;
  if (value == null || value === '') return null;
  return value;
}

export function diskProvisionedIopsLabel(resource, metricsData = null) {
  const value = diskProvisionedIops(resource, metricsData);
  if (value == null) return '—';
  return formatProvisionedCount(value);
}

export function diskProvisionedMbpsLabel(resource, metricsData = null) {
  const value = diskProvisionedMbps(resource, metricsData);
  if (value == null) return '—';
  return `${formatProvisionedCount(value)} MB/s`;
}

export function diskSizeGbLabel(resource, metricsData = null) {
  const props = normalizeDiskProperties(resource, metricsData);
  const sizeGb = props.diskSizeGB;
  if (sizeGb == null || sizeGb === '') return '—';
  const size = Number(sizeGb);
  return Number.isFinite(size) ? `${size.toLocaleString()} GB` : `${sizeGb} GB`;
}

export function diskLastOwnershipUpdate(resource) {
  if (!resource) return null;
  return diskPropertyValue(resource.properties || {}, 'lastOwnershipUpdateTime') || null;
}

export function diskSku(resource) {
  return toDisplayText(resource?.sku?.name || resource?.sku || resource?._sku);
}

export function diskStateLabel(resource) {
  const props = normalizeDiskProperties(resource);
  return formatPowerState(props.diskState || resource?.state || resource?._state);
}

function diskStateTone(state) {
  const value = String(state || '').toLowerCase();
  if (value.includes('attached') && !value.includes('unattached')) return 'ok';
  if (value.includes('unattached')) return 'warn';
  return 'muted';
}

function addDiskTile(tiles, key, label, value, extra = {}) {
  if (value == null || value === '' || value === '—') return;
  tiles.push({ key, label, value, ...extra });
}

function addAttachmentTiles(tiles, armId, { keyPrefix, labelPrefix = '' } = {}) {
  if (!armId) return;

  const attachment = parseComputeHostAttachment(armId);
  const prefix = labelPrefix ? `${labelPrefix} ` : '';

  const attachedLabel = prefix ? `${prefix}attached to` : 'Attached to';
  const computeTypeLabel = prefix ? `${prefix}compute type` : 'Compute type';

  if (!attachment) {
    addDiskTile(tiles, `${keyPrefix}-host`, attachedLabel, shortArmResourceLabel(armId) || armId, {
      linkValue: armId,
    });
    return;
  }

  addDiskTile(tiles, `${keyPrefix}-type`, computeTypeLabel, attachment.typeLabel);
  addDiskTile(tiles, `${keyPrefix}-host`, attachedLabel, attachment.displayLabel, {
    attachment,
  });

  if (attachment.kind === 'vmss_instance' && attachment.parentResourceId) {
    addDiskTile(tiles, `${keyPrefix}-vmss`, 'Scale set', attachment.name, {
      attachment: {
        ...attachment,
        resourceId: attachment.parentResourceId,
        displayLabel: attachment.name,
        inventoryLink: attachment.scaleSetInventoryLink,
        portalLink: attachment.scaleSetPortalLink,
      },
    });
  }
}

/** Resolve current or last compute host for a disk (VM or VMSS). */
export function getDiskHostAttachment(resource) {
  const props = normalizeDiskProperties(resource);

  const primaryHostId = props.managedBy
    || (Array.isArray(props.managedByExtended) && props.managedByExtended[0])
    || (Array.isArray(props.shareInfo) && (props.shareInfo[0]?.vmUri || props.shareInfo[0]?.VmUri));

  if (primaryHostId) {
    return {
      status: 'attached',
      armId: primaryHostId,
      attachment: parseComputeHostAttachment(primaryHostId),
    };
  }

  const lastManagedBy = props.lastManagedBy;
  if (lastManagedBy) {
    return {
      status: 'last_attached',
      armId: lastManagedBy,
      attachment: parseComputeHostAttachment(lastManagedBy),
    };
  }

  const state = diskStateLabel(resource);
  if (String(state).toLowerCase().includes('unattached')) {
    return { status: 'unattached', armId: null, attachment: null };
  }

  return { status: 'unknown', armId: null, attachment: null };
}

/** Compact label for disk tables (VM name, VMSS / instance, or Unattached). */
export function diskAttachmentSummary(resource) {
  const host = getDiskHostAttachment(resource);
  if (host.status === 'unattached') return 'Unattached';
  if (host.attachment?.displayLabel) return host.attachment.displayLabel;
  if (host.armId) return shortArmResourceLabel(host.armId) || host.armId;
  return '—';
}

export function diskAttachmentTypeLabel(resource) {
  const host = getDiskHostAttachment(resource);
  if (host.attachment?.typeLabel) return host.attachment.typeLabel;
  if (host.status === 'unattached') return null;
  return null;
}

function formatAvgMaxStat(row, { provisionedCap = null, capUnit = '' } = {}) {
  const stats = row?.stats || {};
  const avg = stats.average ?? stats.avg ?? row?.value;
  const max = stats.maximum ?? stats.max;
  const unit = row?.unit;
  const factKey = row?.fact_key || row?.factKey;
  if (avg == null && max == null) return null;
  const avgText = avg != null ? formatMetricStatValue(factKey, avg, unit) : null;
  const maxText = max != null ? formatMetricStatValue(factKey, max, unit) : null;
  let text;
  if (avgText && maxText && avgText !== maxText) text = `${avgText} avg · ${maxText} max`;
  else text = avgText || maxText;

  if (text && provisionedCap != null && provisionedCap !== '') {
    const capText = capUnit === 'MB/s'
      ? `${formatProvisionedCount(provisionedCap)} MB/s`
      : formatProvisionedCount(provisionedCap);
    text = `${text} · ${capText} provisioned`;
  }
  return text;
}

/** Azure Monitor usage rows for disk drawer (IOPS, throughput, queue depth, used %). */
export function getDiskUsageMetricRows(metricsData) {
  if (!metricsData?.ok) return [];

  const fromArrays = [
    ...(metricsData.metrics || []),
    ...(metricsData.derived || []),
    ...(metricsData.metrics_detail || []),
  ]
    .map((row) => normalizeMetricRow(row))
    .filter(Boolean);

  const byKey = new Map();
  for (const row of fromArrays) {
    if (row.fact_key) byKey.set(row.fact_key, row);
  }

  if (!byKey.size && metricsData.facts && typeof metricsData.facts === 'object') {
    for (const factKey of DISK_USAGE_FACT_KEYS) {
      const value = metricsData.facts[factKey];
      if (value == null || value === '') continue;
      byKey.set(factKey, normalizeMetricRow({
        fact_key: factKey,
        label: labelForFactKey(factKey),
        stats: { average: value, maximum: value },
      }));
    }
  }

  return DISK_USAGE_FACT_KEYS
    .map((factKey) => byKey.get(factKey))
    .filter(Boolean);
}

export function getDiskUsageTiles(metricsData, { resource = null } = {}) {
  const provisionedIops = diskProvisionedIops(resource, metricsData);
  const provisionedMbps = diskProvisionedMbps(resource, metricsData);

  return getDiskUsageMetricRows(metricsData)
    .map((row) => {
      let provisionedCap = null;
      let capUnit = '';
      if (row.fact_key === 'disk_read_iops' || row.fact_key === 'disk_write_iops') {
        provisionedCap = provisionedIops;
      }
      if (row.fact_key === 'disk_read_bps' || row.fact_key === 'disk_write_bps') {
        provisionedCap = provisionedMbps;
        capUnit = 'MB/s';
      }
      const value = formatAvgMaxStat(row, { provisionedCap, capUnit });
      if (!value) return null;
      return {
        key: `usage-${row.fact_key}`,
        label: row.label || labelForFactKey(row.fact_key),
        value,
        section: 'usage',
      };
    })
    .filter(Boolean);
}

function addProvisionedCapacityTiles(tiles, resource, metricsData = null) {
  const sizeLabel = diskSizeGbLabel(resource, metricsData);
  if (sizeLabel !== '—') {
    addDiskTile(tiles, 'size', 'Provisioned size', sizeLabel);
  }

  const iops = diskProvisionedIops(resource, metricsData);
  if (iops != null) {
    addDiskTile(tiles, 'iops', 'Provisioned IOPS', formatProvisionedCount(iops));
  }

  const mbps = diskProvisionedMbps(resource, metricsData);
  if (mbps != null) {
    addDiskTile(tiles, 'mbps', 'Provisioned throughput', `${formatProvisionedCount(mbps)} MB/s`);
  }
}

/** Grouped drawer sections for compact disk insight layout. */
export function getDiskDrawerSections(resource, metricsData = null) {
  if (!resource) return [];

  const props = normalizeDiskProperties(resource, metricsData);
  const state = diskStateLabel(resource);
  const sections = [];

  const identityTiles = [];
  addDiskTile(identityTiles, 'sku', 'SKU', diskSku(resource));
  if (state && state !== 'Unknown') {
    addDiskTile(identityTiles, 'disk-state', 'Disk state', state, { tone: diskStateTone(state) });
  }
  if (identityTiles.length) {
    sections.push({ id: 'identity', label: 'Disk', tiles: identityTiles });
  }

  const capacityTiles = [];
  addProvisionedCapacityTiles(capacityTiles, resource, metricsData);
  if (capacityTiles.length) {
    sections.push({ id: 'provisioned', label: 'Provisioned capacity', tiles: capacityTiles });
  }

  const attachmentTiles = [];
  const managedBy = props.managedBy;
  if (managedBy) {
    addAttachmentTiles(attachmentTiles, managedBy, { keyPrefix: 'attached' });
  } else if (String(state).toLowerCase().includes('unattached')) {
    addDiskTile(attachmentTiles, 'attached-to', 'Attached to', 'Unattached');
    const lastManagedBy = props.lastManagedBy;
    if (lastManagedBy) {
      addAttachmentTiles(attachmentTiles, lastManagedBy, { keyPrefix: 'last', labelPrefix: 'Last' });
    }
  } else {
    const lastManagedBy = props.lastManagedBy;
    if (lastManagedBy) {
      addAttachmentTiles(attachmentTiles, lastManagedBy, { keyPrefix: 'last', labelPrefix: 'Last' });
    }
  }
  if (attachmentTiles.length) {
    sections.push({ id: 'attachment', label: 'Compute host', tiles: attachmentTiles });
  }

  const metaTiles = [];
  const provisioningState = props.provisioningState;
  if (provisioningState) {
    addDiskTile(metaTiles, 'provisioning', 'Provisioning state', toDisplayText(provisioningState));
  }
  if (props.timeCreated) {
    addDiskTile(metaTiles, 'created', 'Created', formatDateTime(props.timeCreated));
  }
  const lastOwnership = diskLastOwnershipUpdate(resource);
  if (lastOwnership) {
    addDiskTile(metaTiles, 'last-ownership', 'Last ownership update', formatDateTime(lastOwnership));
  }
  if (resource.syncedAt) {
    addDiskTile(metaTiles, 'synced', 'Last synced', formatDateTime(resource.syncedAt));
  }
  if (metaTiles.length) {
    sections.push({ id: 'metadata', label: 'Lifecycle', tiles: metaTiles });
  }

  return sections;
}

/** Disk-specific property tiles for the insight drawer summary (flat list). */
export function getDiskPropertyTiles(resource, metricsData = null) {
  return getDiskDrawerSections(resource, metricsData).flatMap((section) => section.tiles);
}

export function getDiskMetricsStatusMessage(metricsData, metricsError) {
  if (metricsError) {
    return typeof metricsError === 'string'
      ? metricsError
      : metricsError?.message || 'Could not load disk metrics.';
  }
  if (!metricsData) return null;
  if (!metricsData.ok) {
    return metricsData.error || metricsData.unavailable_reason || 'Metrics not available for this disk.';
  }
  if (getDiskUsageMetricRows(metricsData).length) return null;
  if (metricsData.inventory_properties?.length) {
    return 'Live Azure Monitor metrics are unavailable. Sync inventory or open Optimization center to refresh usage.';
  }
  return 'No usage metrics yet. Sync from Azure or run analysis to populate disk I/O and capacity data.';
}

export function diskUsageSectionLabel(timespan) {
  const period = metricTimespanLabel(timespan);
  return period ? `Usage · ${period}` : 'Usage';
}

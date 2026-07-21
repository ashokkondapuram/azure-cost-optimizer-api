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
import {
  diskAssessmentMetricLabel,
  diskAssessmentPropertyGroupDefs,
} from '../../../disks/diskAssessment';

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

const DISK_CANVAS_METRIC_KEYS = [
  'disk_iops_utilization_pct',
  'disk_throughput_utilization_pct',
  'disk_queue_depth',
  'disk_used_pct',
];

const DISK_MAJOR_PROPERTY_LABELS = new Set([
  'sku', 'disk state', 'disk size', 'provisioned size', 'size', 'state',
  'attached to', 'managed by', 'provisioning state', 'encryption',
  'encryption settings', 'provisioned iops', 'provisioned throughput', 'performance tier',
]);

const DISK_ASSESSMENT_MAJOR_ARM_PATHS = new Set([
  'sku.name',
  'properties.diskSizeGB',
  'properties.diskState',
  'properties.managedBy',
  'properties.provisioningState',
  'properties.diskIOPSReadWrite',
  'properties.diskMBpsReadWrite',
  'properties.encryption',
  'properties.tier',
]);

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

/** Resolve a nested ARM path from a disk resource (properties_json or flattened API fields). */
export function getDiskPropertyValue(resource, armPath, metricsData = null) {
  if (!resource || !armPath) return undefined;

  const props = normalizeDiskProperties(resource, metricsData);

  if (armPath === 'sku.name') {
    return resource.sku?.name
      || (typeof resource.sku === 'string' ? resource.sku : undefined)
      || props.sku;
  }
  if (armPath === 'location') {
    return resource.location || resource.region;
  }
  if (armPath === 'zones') {
    return resource.zones;
  }

  if (armPath.startsWith('properties.')) {
    const leaf = armPath.slice('properties.'.length);
    return diskPropertyValue(props, leaf) ?? diskPropertyValue(resource.properties || {}, leaf);
  }

  const parts = armPath.split('.');
  let current = resource;
  for (const part of parts) {
    if (current == null) return undefined;
    current = current[part];
  }
  return current;
}

function formatDiskArrayValue(value) {
  if (!Array.isArray(value) || !value.length) return null;
  if (typeof value[0] === 'object' && value[0] != null) {
    const parts = value.map((entry) => {
      if (typeof entry === 'string') return entry;
      const uri = entry.vmUri || entry.VmUri || entry.id || entry.Id;
      if (uri) return shortArmResourceLabel(uri) || uri;
      const option = entry.createOption || entry.CreateOption;
      if (option) return toDisplayText(option);
      return toDisplayText(JSON.stringify(entry));
    });
    return parts.filter(Boolean).join(', ');
  }
  return value.map((item) => toDisplayText(item)).filter(Boolean).join(', ');
}

function formatDiskObjectValue(value, armPath) {
  if (!value || typeof value !== 'object') return toDisplayText(value);

  if (armPath === 'properties.encryption') {
    return diskEncryptionLabel(value) || toDisplayText(value);
  }

  if (armPath === 'properties.creationData') {
    const option = value.createOption || value.CreateOption;
    if (option) return toDisplayText(option);
    const source = value.sourceResourceId || value.SourceResourceId;
    if (source) return shortArmResourceLabel(source) || source;
    const uploadSize = value.uploadSizeBytes ?? value.UploadSizeBytes;
    if (uploadSize != null) return `${Number(uploadSize).toLocaleString()} bytes`;
  }

  if (armPath === 'properties.securityProfile') {
    const type = value.securityType || value.SecurityType;
    if (type) return toDisplayText(type);
  }

  const type = value.type || value.Type;
  if (type) return toDisplayText(type);
  const keys = Object.keys(value);
  if (keys.length === 1) return toDisplayText(value[keys[0]]);
  return toDisplayText(JSON.stringify(value));
}

/** Format a raw disk property value using assessment type and unit metadata. */
export function formatDiskAssessmentPropertyValue(rawValue, propDef, resource = null, metricsData = null) {
  if (rawValue == null || rawValue === '') return '—';

  const { type, unit, arm_path: armPath } = propDef || {};
  const path = armPath || propDef?.armPath;

  if (path === 'properties.diskState') {
    return formatPowerState(rawValue);
  }

  if (path === 'properties.managedBy' && typeof rawValue === 'string') {
    const attachment = parseComputeHostAttachment(rawValue);
    return attachment?.displayLabel || shortArmResourceLabel(rawValue) || rawValue;
  }

  if (path === 'properties.diskAccessId' && typeof rawValue === 'string') {
    return shortArmResourceLabel(rawValue) || rawValue;
  }

  if (path === 'location') {
    return toDisplayText(rawValue);
  }

  if (type === 'boolean') {
    return rawValue ? 'Yes' : 'No';
  }

  if (type === 'datetime') {
    return formatDateTime(rawValue);
  }

  if (type === 'array') {
    return formatDiskArrayValue(rawValue) || '—';
  }

  if (type === 'object') {
    return formatDiskObjectValue(rawValue, path) || '—';
  }

  if (type === 'number') {
    const num = Number(rawValue);
    if (!Number.isFinite(num)) return toDisplayText(rawValue);
    if (unit === 'GB') return `${num.toLocaleString()} GB`;
    if (unit === 'IOPS') return formatProvisionedCount(num);
    if (unit === 'MB/s') return `${formatProvisionedCount(num)} MB/s`;
    if (unit === '%') return `${num}%`;
    return unit ? `${formatProvisionedCount(num)} ${unit}` : formatProvisionedCount(num);
  }

  if (path === 'sku.name') {
    return diskSku(resource || { sku: rawValue });
  }

  return toDisplayText(rawValue);
}

/**
 * Build assessment property sections from azure_properties.groups.
 * Returns only properties defined in the assessment schema.
 */
export function buildDiskPropertiesSections(resource, metricsData = null, { hideEmpty = true } = {}) {
  if (!resource) return [];

  const sections = [];
  for (const group of diskAssessmentPropertyGroupDefs()) {
    const items = [];
    for (const prop of group.properties || []) {
      const raw = getDiskPropertyValue(resource, prop.arm_path, metricsData);
      const formatted = formatDiskAssessmentPropertyValue(raw, prop, resource, metricsData);
      if (hideEmpty && (formatted == null || formatted === '' || formatted === '—')) continue;

      const item = {
        label: prop.label,
        value: formatted,
        displayValue: formatted,
        arm_path: prop.arm_path,
        type: prop.type,
        major: DISK_ASSESSMENT_MAJOR_ARM_PATHS.has(prop.arm_path)
          || DISK_MAJOR_PROPERTY_LABELS.has(String(prop.label || '').toLowerCase()),
      };

      if (prop.arm_path === 'properties.managedBy' && raw) {
        item.linkValue = raw;
        item.attachment = parseComputeHostAttachment(raw);
      }
      if (prop.arm_path === 'properties.diskAccessId' && raw) {
        item.linkValue = raw;
      }

      items.push(item);
    }

    if (items.length) {
      sections.push({
        id: group.group,
        label: group.title,
        group: group.group,
        items,
      });
    }
  }

  return sections;
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

  const skuName = diskSku(resource);
  if (skuName && skuName !== '—' && !normalized.sku) {
    normalized.sku = skuName;
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

function diskEncryptionLabel(props) {
  const enc = props?.encryption || props?.Encryption;
  if (!enc) return null;
  if (typeof enc === 'string') return toDisplayText(enc);
  const type = enc.type || enc.Type || '';
  if (String(type).includes('Platform')) return 'Platform-managed';
  if (String(type).includes('Customer')) return 'Customer-managed';
  return toDisplayText(type) || 'Enabled';
}

function diskStateTone(state) {
  const value = String(state || '').toLowerCase();
  if (value.includes('attached') && !value.includes('unattached')) return 'ok';
  if (value.includes('unattached')) return 'warn';
  return 'muted';
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

/** Grouped drawer sections for compact disk insight layout. */
export function getDiskDrawerSections(resource, metricsData = null) {
  return buildDiskPropertiesSections(resource, metricsData).map((section) => ({
    id: section.id,
    label: section.label,
    tiles: (section.items || []).map((item) => ({
      key: String(item.arm_path || item.label).replace(/\./g, '-'),
      label: item.label,
      value: item.value,
      tone: item.arm_path === 'properties.diskState' ? diskStateTone(item.value) : undefined,
      linkValue: item.linkValue,
      attachment: item.attachment,
    })),
  }));
}

/** Disk-specific property tiles for the insight drawer summary (flat list). */
export function getDiskPropertyTiles(resource, metricsData = null) {
  return getDiskDrawerSections(resource, metricsData).flatMap((section) => section.tiles);
}

/** Convert disk drawer sections to insight-canvas property groups. */
export function diskDrawerSectionsToPropertyGroups(resource, metricsData = null) {
  return buildDiskPropertiesSections(resource, metricsData)
    .map((section) => ({
      title: section.label,
      items: (section.items || [])
        .map((item) => ({
          label: item.label,
          value: toDisplayText(item.displayValue ?? item.value),
          major: item.major,
          fact_key: item.arm_path,
        }))
        .filter((item) => item.value && item.value !== '—'),
    }))
    .filter((group) => group.items.length > 0);
}

const PROPERTY_GROUP_ORDER = ['configuration', 'capacity', 'attachment', 'security'];

function isEmptyConceptPropertyValue(value) {
  const v = String(value ?? '').trim();
  return !v || v === '—' || v === '-' || v === 'N/A';
}

/**
 * Property groups — exact match to design/concept-v2/js/disks/index.js buildPropertyGroups.
 */
export function buildDiskConceptPropertyGroups(disk) {
  const p = disk?.properties || normalizeDiskProperties(disk);
  const groupsByKey = {
    configuration: {
      group: 'configuration',
      title: 'Disk',
      items: [
        { label: 'Disk size', value: p.diskSizeGB != null ? `${p.diskSizeGB} GB` : '—', major: true },
        { label: 'SKU', value: p.sku, major: true },
        { label: 'Performance tier', value: p.tier },
        { label: 'Disk state', value: p.diskState, major: true },
        { label: 'Provisioning state', value: p.provisioningState, major: true },
        { label: 'Created', value: p.timeCreated },
        { label: 'Bursting enabled', value: p.burstingEnabled != null ? (p.burstingEnabled ? 'Yes' : 'No') : null },
      ],
    },
    capacity: {
      group: 'capacity',
      title: 'Provisioned capacity',
      items: [
        { label: 'Provisioned IOPS', value: p.diskIOPSReadWrite != null ? Number(p.diskIOPSReadWrite).toLocaleString('en-US') : null },
        { label: 'Provisioned throughput', value: p.diskMBpsReadWrite != null ? `${p.diskMBpsReadWrite} MB/s` : null },
      ],
    },
    attachment: {
      group: 'attachment',
      title: 'Compute host',
      items: [
        { label: 'Attached to', value: p.managedBy, major: true },
        { label: 'Last ownership update', value: p.lastOwnershipUpdateTime },
        { label: 'Creation source', value: p.creationSource },
      ],
    },
    security: {
      group: 'security',
      title: 'Security',
      items: [
        { label: 'Encryption settings', value: p.encryption, major: true },
        { label: 'Network access policy', value: p.networkAccessPolicy },
        { label: 'Public network access', value: p.publicNetworkAccess },
      ],
    },
  };

  return PROPERTY_GROUP_ORDER
    .map((key) => {
      const g = groupsByKey[key];
      if (!g) return null;
      const items = g.items.filter((item) => !isEmptyConceptPropertyValue(item.value));
      return items.length ? { ...g, items } : null;
    })
    .filter(Boolean);
}

function metricRowFromFactKey(metricsData, factKey, resource = null) {
  const rows = [
    ...(metricsData?.metrics || []),
    ...(metricsData?.derived || []),
    ...(metricsData?.metrics_detail || []),
  ];
  const match = rows
    .map((row) => normalizeMetricRow(row))
    .find((row) => row?.fact_key === factKey);
  if (match) return match;

  const facts = metricsData?.facts || resource?._technical_facts || resource?._metrics || {};
  const value = facts[factKey];
  if (value == null || value === '') return null;
  return normalizeMetricRow({
    fact_key: factKey,
    label: labelForFactKey(factKey),
    stats: { average: value, maximum: value },
    unit: String(factKey).includes('_pct') ? '%' : undefined,
  });
}

/** Insight canvas metric cards for disks — assessment-derived utilization first. */
export function buildDiskCanvasMetrics(metricsData, resource = null) {
  if (!metricsData && !resource) return [];

  return DISK_CANVAS_METRIC_KEYS
    .map((factKey) => {
      const row = metricRowFromFactKey(metricsData, factKey, resource);
      if (!row) return null;

      const label = diskAssessmentMetricLabel(factKey) || labelForFactKey(factKey, row.label);
      const stats = row.stats || {};
      const raw = stats.maximum ?? stats.average ?? row.value;
      const value = formatMetricStatValue(factKey, raw, row.unit);
      let pct = null;
      if (raw != null && String(factKey).includes('_pct')) {
        const num = Number(raw);
        if (Number.isFinite(num)) {
          pct = Math.min(100, Math.max(0, num <= 1 ? num * 100 : num));
        }
      }
      return {
        label,
        value: toDisplayText(value),
        pct,
        fact_key: factKey,
      };
    })
    .filter((m) => m?.label && m.value && m.value !== '—');
}

function diskSkuSpecs(resource, metricsData = null) {
  const props = normalizeDiskProperties(resource, metricsData);
  const specs = [];
  const tier = props.tier || diskSku(resource);
  if (tier && tier !== '—') specs.push({ label: 'Tier', value: tier });
  const iops = diskProvisionedIopsLabel(resource, metricsData);
  if (iops !== '—') specs.push({ label: 'IOPS', value: iops });
  const throughput = diskProvisionedMbpsLabel(resource, metricsData);
  if (throughput !== '—') specs.push({ label: 'Throughput', value: throughput });
  const size = diskSizeGbLabel(resource, metricsData);
  if (size !== '—') specs.push({ label: 'Size', value: size });
  return specs;
}

/** SKU panel shape for insight canvas (current + recommended). */
export function buildDiskSkuPanel(finding, row, metricsData = null, { cost = 0, savings = 0, mtdCost = 0 } = {}) {
  const props = normalizeDiskProperties(row, metricsData);
  const skuName = diskSku(row);
  const tierLabel = props.tier || skuName;
  const sizeLabel = diskSizeGbLabel(row, metricsData);
  const changeType = finding?.category?.code || finding?.category || 'Tier change';
  const target = finding?.recommended_sku || finding?.target_sku || finding?.target_tier;
  const targetName = typeof target === 'string'
    ? target
    : toDisplayText(target?.name || target?.tier || finding?.recommended_tier);

  const current = {
    name: tierLabel && tierLabel !== '—' ? `${tierLabel} ${sizeLabel !== '—' ? sizeLabel : ''}`.trim() : skuName,
    tier: tierLabel,
    size: sizeLabel,
    region: row?.location || row?.region,
    specs: diskSkuSpecs(row, metricsData),
    monthlyCost: cost,
    mtdCost: mtdCost > 0 ? mtdCost : undefined,
  };

  let targetBlock = null;
  if (targetName && targetName !== '—' && !/delete/i.test(String(changeType))) {
    targetBlock = {
      name: targetName,
      tier: targetName,
      size: sizeLabel,
      region: row?.location || row?.region,
      specs: diskSkuSpecs({ ...row, sku: targetName, properties: { ...props, tier: targetName } }, metricsData),
      monthlyCost: Math.max(0, cost - savings),
    };
  }

  return {
    changeType: typeof changeType === 'string' ? changeType : 'Tier change',
    current,
    target: /delete/i.test(String(changeType)) ? null : targetBlock,
  };
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
    return 'Live Azure Monitor metrics are unavailable. Sync inventory or open Sync center to refresh usage.';
  }
  return 'No usage metrics yet. Sync from Azure or run analysis to populate disk I/O and capacity data.';
}

export function diskUsageSectionLabel(timespan) {
  const period = metricTimespanLabel(timespan);
  return period ? `Usage · ${period}` : 'Usage';
}

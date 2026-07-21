/** Storage account helpers — owned by storage-account IT service (frontend). */

import { toDisplayText } from '../../../utils/formatDisplay';
import { formatServiceFact, MISSING_DISPLAY } from '../../../utils/serviceDisplayUtils';

export { MISSING_DISPLAY };

const ACCESS_TIER_LABELS = {
  Hot: 'Hot',
  Cool: 'Cool',
  Archive: 'Archive',
};

const REPLICATION_LABELS = {
  STANDARD_LRS: 'Standard locally redundant (LRS)',
  STANDARD_ZRS: 'Standard zone-redundant (ZRS)',
  STANDARD_GRS: 'Standard geo-redundant (GRS)',
  STANDARD_GZRS: 'Standard geo-zone-redundant (GZRS)',
  STANDARD_RAGRS: 'Standard read-access geo-redundant (RA-GRS)',
  STANDARD_RAGZRS: 'Standard read-access geo-zone-redundant (RA-GZRS)',
  LRS: 'Locally redundant (LRS)',
  ZRS: 'Zone-redundant (ZRS)',
  GRS: 'Geo-redundant (GRS)',
  GZRS: 'Geo-zone-redundant (GZRS)',
  RAGRS: 'Read-access geo-redundant (RA-GRS)',
  RAGZRS: 'Read-access geo-zone-redundant (RA-GZRS)',
};

const STORAGE_PROPERTY_ALIASES = {
  accessTier: ['accessTier', 'AccessTier', 'access_tier'],
  kind: ['kind', 'Kind'],
  sku: ['sku', 'Sku'],
  supportsHttpsTrafficOnly: ['supportsHttpsTrafficOnly', 'SupportsHttpsTrafficOnly'],
  allowBlobPublicAccess: ['allowBlobPublicAccess', 'AllowBlobPublicAccess'],
  minimumTlsVersion: ['minimumTlsVersion', 'MinimumTlsVersion'],
  provisioningState: ['provisioningState', 'ProvisioningState'],
};

export function isStorageResource(resource, apiPath = '') {
  const type = (resource?.type || '').toLowerCase();
  if (type.includes('storageaccounts')) return true;
  return String(apiPath || '').includes('/storage');
}

export function storagePropertyValue(source, canonicalKey) {
  if (!source || typeof source !== 'object') return undefined;
  const aliases = STORAGE_PROPERTY_ALIASES[canonicalKey] || [canonicalKey];
  for (const key of aliases) {
    const value = source[key];
    if (value != null && value !== '') return value;
  }
  if (canonicalKey === 'sku') {
    const sku = source.sku;
    if (sku && typeof sku === 'object' && sku.name) return sku.name;
  }
  return undefined;
}

export function formatAccessTier(tier) {
  if (tier == null || tier === '') return '—';
  const text = String(tier).trim();
  return ACCESS_TIER_LABELS[text] || text;
}

export function formatReplicationSku(skuName) {
  if (skuName == null || skuName === '') return '—';
  const key = String(skuName).trim().toUpperCase();
  return REPLICATION_LABELS[key] || key.replace(/_/g, ' ');
}

export function formatStorageMetric(factKey, value) {
  return formatServiceFact(factKey, value);
}

export function normalizeStorageProperties(resource) {
  const raw = resource?.properties || {};
  const normalized = { ...raw };
  for (const canonicalKey of Object.keys(STORAGE_PROPERTY_ALIASES)) {
    const value = storagePropertyValue(raw, canonicalKey) ?? storagePropertyValue(resource, canonicalKey);
    if (value != null && value !== '') normalized[canonicalKey] = value;
  }
  const skuName = storagePropertyValue(resource, 'sku') || resource?.sku?.name;
  if (skuName) {
    normalized.sku_name = skuName;
    normalized.sku_display = formatReplicationSku(skuName);
  }
  const tier = storagePropertyValue(normalized, 'accessTier');
  if (tier) normalized.access_tier_display = formatAccessTier(tier);
  return normalized;
}

export function storagePropertyRows(resource) {
  const props = normalizeStorageProperties(resource);
  const rows = [];
  const tier = props.accessTier || props.access_tier;
  if (tier != null && tier !== '') {
    rows.push({ label: 'Access tier', value: formatAccessTier(tier) });
  }
  const kind = props.kind;
  if (kind != null && kind !== '') {
    rows.push({ label: 'Storage kind', value: toDisplayText(kind) });
  }
  const sku = props.sku_display || formatReplicationSku(props.sku_name);
  if (sku && sku !== '—') {
    rows.push({ label: 'Replication', value: sku });
  }
  if (props.supportsHttpsTrafficOnly != null) {
    rows.push({
      label: 'HTTPS only',
      value: props.supportsHttpsTrafficOnly ? 'Yes' : 'No',
    });
  }
  if (props.allowBlobPublicAccess != null) {
    rows.push({
      label: 'Public blob access',
      value: props.allowBlobPublicAccess ? 'Allowed' : 'Blocked',
    });
  }
  if (props.minimumTlsVersion != null && props.minimumTlsVersion !== '') {
    rows.push({ label: 'Minimum TLS', value: toDisplayText(props.minimumTlsVersion) });
  }
  return rows;
}

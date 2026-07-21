import { formatPropertyValue, isBooleanPropertyKey } from './format';
import { formatFactValue } from './resourceMetricsUtils';
import { resolvePropertyLabel, EMPTY_PROPERTY_DISPLAY } from './serviceDisplayUtils';
import { essentialsRowMatchKey, isOverviewEssentialRow } from './drawerOverviewDedupe';

const ARM_PROPERTY_SKIP = new Set([
  'provisioningState',
]);

const INVENTORY_META_SKIP = new Set([
  'monthly_cost_usd',
  'metrics_available',
]);

const ARM_TYPED_VALUE_TYPES = new Set([
  'bool',
  'string',
  'int',
  'securestring',
  'object',
  'array',
  'secureobject',
]);

const PROPERTY_CONTAINER_KEYS = new Set([
  'parameters',
  'properties',
]);

/**
 * @param {unknown} value
 */
function isArmTypedValue(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  if (!('type' in value) || !('value' in value)) return false;
  const typeName = String(value.type ?? '').trim();
  if (!typeName) return false;
  return ARM_TYPED_VALUE_TYPES.has(typeName.toLowerCase());
}

function isArmTypeMetadata(value) {
  return ARM_TYPED_VALUE_TYPES.has(String(value ?? '').trim().toLowerCase());
}

/**
 * @param {string} path
 */
function labelFromPropertyPath(path) {
  const configured = resolvePropertyLabel(path);
  if (configured) return configured;

  const segments = String(path || '').split('.').filter(Boolean);
  if (!segments.length) return 'Property';

  const leaf = segments[segments.length - 1];
  const leafLabel = resolvePropertyLabel(leaf) || humanizePropertyKey(leaf);

  if (segments.length <= 2) return leafLabel;

  const parent = segments[segments.length - 2];
  if (PROPERTY_CONTAINER_KEYS.has(parent.toLowerCase())) {
    return leafLabel;
  }

  const parentLabel = resolvePropertyLabel(parent) || humanizePropertyKey(parent);
  return `${parentLabel} · ${leafLabel}`;
}

/** Drop ARM schema noise rows such as Type: Bool / Value: No pairs. */
export function isNoisePropertyRow(row) {
  if (!row) return true;
  const label = String(row.label || '').trim().toLowerCase();
  const factKey = String(row.fact_key || '').trim().toLowerCase();
  const rawValue = row.value ?? row.formatted;

  if (label === 'type' && isArmTypeMetadata(rawValue)) return true;
  if (label === 'value' && factKey.endsWith('.value')) return true;
  if (factKey.endsWith('.type') && isArmTypeMetadata(rawValue)) return true;
  return false;
}

/**
 * @param {string} key
 */
export function humanizePropertyKey(key) {
  if (!key) return 'Property';
  const leaf = String(key).split('.').pop() || key;
  const configured = resolvePropertyLabel(leaf) || resolvePropertyLabel(key);
  if (configured) return toSentenceCaseLabel(configured);
  const words = leaf
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim();
  return toSentenceCaseLabel(words);
}

const LABEL_ACRONYMS = new Set(['sku', 'id', 'iops', 'mbps', 'gb', 'ip', 'dns', 'ssl', 'https', 'os', 'vm', 'aks', 'uri', 'url', 'fqdn']);

/** Sentence case for drawer property labels (SKU and common acronyms stay uppercase). */
export function toSentenceCaseLabel(text) {
  const raw = String(text || '').trim();
  if (!raw) return 'Property';
  return raw
    .split(/\s+/)
    .map((word, index) => {
      const lower = word.toLowerCase();
      if (LABEL_ACRONYMS.has(lower)) return lower.toUpperCase();
      if (index === 0) return lower.charAt(0).toUpperCase() + lower.slice(1);
      return lower;
    })
    .join(' ');
}

function formatTypedArmValue(path, typed) {
  const raw = typed.value;
  if (raw == null || raw === '') return EMPTY_PROPERTY_DISPLAY;
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const innerRows = flattenPropertyRows(raw, path, 3).filter((row) => !isNoisePropertyRow(row));
    if (innerRows.length === 1) return innerRows[0].formatted;
    if (innerRows.length > 1) {
      return innerRows.map((row) => `${row.label}: ${row.formatted}`).join('; ');
    }
    return formatPropertyValue(raw, { key: path });
  }
  return formatScalarValue(path, raw);
}

function makePropertyRow(path, value, formatted = null) {
  return {
    fact_key: path,
    label: labelFromPropertyPath(path),
    value,
    formatted: formatted ?? formatScalarValue(path, value),
  };
}

/**
 * Flatten nested ARM/inventory values into table rows.
 * @param {unknown} value
 * @param {string} [prefix]
 * @param {number} [maxDepth]
 */
export function flattenPropertyRows(value, prefix = '', maxDepth = 4) {
  if (value == null || value === '') return [];

  if (isArmTypedValue(value) && prefix) {
    return [makePropertyRow(prefix, value.value, formatTypedArmValue(prefix, value))];
  }

  if (typeof value !== 'object' || Array.isArray(value) || maxDepth <= 0) {
    const leaf = prefix.split('.').pop() || prefix || 'value';
    return [makePropertyRow(prefix || leaf, value)];
  }

  const rows = [];
  for (const [key, child] of Object.entries(value)) {
    if (child == null || child === '') continue;
    const path = prefix ? `${prefix}.${key}` : key;

    if (isArmTypedValue(child)) {
      rows.push(makePropertyRow(path, child.value, formatTypedArmValue(path, child)));
      continue;
    }

    if (typeof child === 'object' && !Array.isArray(child) && maxDepth > 1) {
      rows.push(...flattenPropertyRows(child, path, maxDepth - 1));
    } else {
      rows.push(makePropertyRow(path, child));
    }
  }
  return rows.filter((row) => !isNoisePropertyRow(row));
}

function formatRowValue(row) {
  const factKey = row.fact_key || '';
  if (!factKey) {
    return row.formatted ?? formatPropertyValue(row.value);
  }
  return formatScalarValue(factKey, row.value, row.unit);
}

function formatScalarValue(key, value, unit = '') {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (isBooleanPropertyKey(key) && (value === 0 || value === 1 || value === '0' || value === '1')) {
    return Number(value) ? 'Yes' : 'No';
  }
  if (typeof value === 'object') {
    return formatPropertyValue(value, { key });
  }
  const formatted = formatFactValue(key, value, unit || undefined);
  if (formatted !== '—') return formatted;
  return formatPropertyValue(value, { key });
}

/** True when a property row has a value worth showing in the drawer. */
export function isDisplayablePropertyRow(row) {
  if (!row) return false;
  const formatted = row.formatted ?? formatRowValue(row);
  if (formatted && formatted !== '—') return true;
  const value = row.value;
  if (value == null || value === '') return false;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

function inventoryRowKey(row) {
  return (row.fact_key || row.label || '').toLowerCase();
}

/**
 * Build drawer nav tabs for ARM + inventory property groups.
 * @param {object} resource
 * @param {object[]} inventoryProperties
 */
export function buildResourcePropertyGroups(resource, inventoryProperties = []) {
  const groups = [];
  const armProps = resource?.properties && typeof resource.properties === 'object'
    ? resource.properties
    : {};

  const scalarRows = [];
  const nestedEntries = [];

  for (const [key, value] of Object.entries(armProps)) {
    if (ARM_PROPERTY_SKIP.has(key)) continue;
    if (value == null || value === '') continue;
    if (typeof value === 'object' && !Array.isArray(value)) {
      nestedEntries.push([key, value]);
    } else {
      scalarRows.push({
        fact_key: key,
        label: humanizePropertyKey(key),
        value,
        formatted: formatScalarValue(key, value),
      });
    }
  }

  const covered = new Set(
    scalarRows.map((row) => inventoryRowKey(row)),
  );

  for (const row of inventoryProperties || []) {
    const key = inventoryRowKey(row);
    if (!key || INVENTORY_META_SKIP.has(key) || covered.has(key)) continue;
    scalarRows.push({
      fact_key: row.fact_key || row.label,
      label: row.label || humanizePropertyKey(row.fact_key),
      value: row.value,
      unit: row.unit,
      formatted: formatRowValue(row),
    });
    covered.add(key);
  }

  const generalRows = scalarRows.filter(isDisplayablePropertyRow).filter((row) => !isNoisePropertyRow(row));
  if (generalRows.length) {
    groups.push({
      id: 'prop:general',
      label: 'General',
      rows: generalRows,
      badge: generalRows.length,
    });
  }

  for (const [key, value] of nestedEntries) {
    const rows = flattenPropertyRows(value, key).filter(isDisplayablePropertyRow).filter((row) => !isNoisePropertyRow(row));
    if (!rows.length) continue;
    groups.push({
      id: `prop:${key}`,
      label: humanizePropertyKey(key),
      rows,
      badge: rows.length,
    });
  }

  return groups;
}

export function propertyGroupTabId(groupId) {
  return groupId.startsWith('prop:') ? groupId : `prop:${groupId}`;
}

export function isPropertyGroupTab(tabId) {
  return String(tabId || '').startsWith('prop:');
}

/** Drop noise and empty property rows. */
export function filterDisplayablePropertyRows(rows = []) {
  return (rows || []).filter((row) => {
    if (isNoisePropertyRow(row)) return false;
    return isDisplayablePropertyRow(row);
  });
}

/** @deprecated Use filterDisplayablePropertyRows — kept for callers during migration. */
export function filterDrawerHeaderPropertyRows(rows = [], seenKeys = null) {
  const seen = seenKeys || new Set();
  return filterDisplayablePropertyRows(rows).filter((row) => {
    const matchKey = essentialsRowMatchKey(row);
    if (matchKey && seen.has(matchKey)) return false;
    if (isOverviewEssentialRow(row) && seen.size > 0) return false;
    if (matchKey) seen.add(matchKey);
    return true;
  });
}

import { formatPropertyMetricValue } from './formatMetricUnits';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatCurrency(amount, { currency = 'CAD', decimals = 2 } = {}) {
  if (amount == null || Number.isNaN(Number(amount))) return '—';
  const value = Number(amount);
  const locale = currency === 'CAD' ? 'en-CA' : 'en-US';
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
  }
}

export function formatCompactCurrency(amount, currency = 'CAD') {
  if (amount == null || Number.isNaN(Number(amount))) return '—';
  const value = Number(amount);
  const sym = currency === 'CAD' ? 'CA$' : '$';
  if (Math.abs(value) >= 1_000_000) return `${sym}${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${sym}${(value / 1_000).toFixed(1)}K`;
  return formatCurrency(value, { currency, decimals: 0 });
}

export function formatDate(value) {
  if (!value) return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
}

/** Format YYYY-MM-DD as Mmm D, YYYY without timezone shift. */
export function formatIsoDate(iso) {
  if (!iso) return '—';
  const parts = String(iso).slice(0, 10).split('-');
  if (parts.length !== 3) return String(iso);
  const year = Number(parts[0]);
  const month = Number(parts[1]) - 1;
  const day = Number(parts[2]);
  if (Number.isNaN(year) || Number.isNaN(month) || Number.isNaN(day)) return String(iso);
  return `${MONTHS[month]} ${day}, ${year}`;
}

export function formatDateRange(startIso, endIso) {
  if (!startIso || !endIso) return '—';
  if (startIso.slice(0, 7) === endIso.slice(0, 7)) {
    const month = MONTHS[Number(startIso.slice(5, 7)) - 1];
    const year = startIso.slice(0, 4);
    const startDay = Number(startIso.slice(8, 10));
    const endDay = Number(endIso.slice(8, 10));
    return `${month} ${startDay} – ${endDay}, ${year}`;
  }
  return `${formatIsoDate(startIso)} – ${formatIsoDate(endIso)}`;
}

export function formatDateTime(value) {
  if (!value) return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const hours = date.getHours();
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const period = hours >= 12 ? 'PM' : 'AM';
  const hour12 = hours % 12 || 12;
  return `${formatDate(date)} at ${hour12}:${minutes} ${period}`;
}

/** Format ISO timestamp in UTC (Azure maintenance windows are UTC). */
export function formatDateTimeUtc(value) {
  if (!value) return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const hours = date.getUTCHours();
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  const period = hours >= 12 ? 'PM' : 'AM';
  const hour12 = hours % 12 || 12;
  const month = MONTHS[date.getUTCMonth()];
  const day = date.getUTCDate();
  const year = date.getUTCFullYear();
  return `${month} ${day}, ${year} at ${hour12}:${minutes} ${period} UTC`;
}

const URL_RE = /^https?:\/\//i;

/** Azure region slug → readable label (eastus2 → East US 2). */
export function humanizeAzureRegion(location) {
  if (location == null || location === '') return '—';
  const text = String(location).trim();
  if (!text) return '—';
  if (/[A-Z]/.test(text) && text.includes(' ')) return text;
  return text
    .replace(/([a-z])([0-9])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function isBooleanPropertyKey(key) {
  const normalized = String(key || '').toLowerCase();
  return normalized.startsWith('enable')
    || normalized.endsWith('enabled')
    || normalized.endsWith('disabled');
}

function formatCosmosLocationEntry(entry) {
  if (entry == null) return '—';
  if (typeof entry !== 'object') return humanizeAzureRegion(entry);
  const region = entry.locationName ?? entry.name ?? entry.id;
  const parts = [humanizeAzureRegion(region)];
  const priority = entry.failoverPriority ?? entry.failover_priority;
  if (priority === 0) parts.push('primary');
  else if (priority != null && priority !== '') parts.push(`failover ${priority}`);
  if (entry.isZoneRedundant) parts.push('zone redundant');
  return parts.filter(Boolean).join(', ');
}

function formatArrayPropertyValue(value, key, { expand = false } = {}) {
  if (!value.length) return 'None';
  const normalizedKey = String(key || '').toLowerCase();

  if (normalizedKey === 'locations' || value.every((item) => item && typeof item === 'object' && 'locationName' in item)) {
    return value.map(formatCosmosLocationEntry).join('; ');
  }

  if (normalizedKey === 'capabilities' || value.every((item) => item && typeof item === 'object' && 'name' in item)) {
    const names = value.map((item) => item.name).filter(Boolean);
    return names.length ? names.join(', ') : 'None';
  }

  if (value.every((item) => item == null || typeof item !== 'object')) {
    return value.map((item) => formatPropertyValue(item, { key })).join(', ');
  }

  if (expand) return JSON.stringify(value, null, 2);
  return `${value.length} item${value.length === 1 ? '' : 's'}`;
}

/** Human-readable property value for inventory tables — avoids [object Object]. */
export function formatPropertyValue(value, { expand = false, key = '' } = {}) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') {
    if (isBooleanPropertyKey(key) && (value === 0 || value === 1)) {
      return value ? 'Yes' : 'No';
    }
    const metricFormatted = formatPropertyMetricValue(key, value);
    if (metricFormatted) return metricFormatted;
    return Number.isFinite(value) ? value.toLocaleString('en-US') : '—';
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return '—';
    if (URL_RE.test(trimmed)) {
      return trimmed;
    }
    if ((trimmed === '0' || trimmed === '1') && isBooleanPropertyKey(key)) {
      return trimmed === '1' ? 'Yes' : 'No';
    }
    return trimmed;
  }
  if (Array.isArray(value)) {
    return formatArrayPropertyValue(value, key, { expand });
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value);
    if (keys.length === 0) return 'Empty';
    const normalizedKey = String(key || '').toLowerCase();
    if (normalizedKey.endsWith('consistencylevel') || normalizedKey === 'defaultconsistencylevel') {
      return String(value.defaultConsistencyLevel ?? value.name ?? keys.map((k) => value[k]).find(Boolean) ?? '—');
    }
    if (expand) return JSON.stringify(value, null, 2);
    return keys
      .slice(0, 4)
      .map((childKey) => `${humanizePropertyKeyInline(childKey)}: ${formatPropertyValue(value[childKey], { key: childKey })}`)
      .join('; ');
  }
  return String(value);
}

function humanizePropertyKeyInline(key) {
  return String(key || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function isComplexPropertyValue(value) {
  if (value == null) return false;
  if (Array.isArray(value)) return value.length > 0;
  return typeof value === 'object';
}

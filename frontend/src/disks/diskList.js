/**
 * Managed disks list — port of design/concept-v2/js/disks/list.js
 */

import { formatCurrency } from '../utils/format';
import {
  DISK_LIST_COLUMNS,
  DISK_LIST_METRICS,
  DISK_LIST_LOCATION,
} from './diskAssessment';

export function formatDiskMetric(value, unit) {
  if (value == null || value === '') return '—';
  return unit === '%' ? `${value}%` : String(value);
}

export function formatDiskCad(amount, currency = 'CAD') {
  if (amount == null || Number.isNaN(Number(amount))) return '—';
  return formatCurrency(amount, { currency, decimals: 2 });
}

export function diskMatchesFilters(disk, { search = '', chip = 'all' } = {}) {
  const q = search.toLowerCase().trim();
  if (q) {
    const parts = [disk.name, disk.resourceGroup, disk.region].map((v) => String(v || '').toLowerCase());
    if (!parts.some((part) => part.includes(q))) return false;
  }
  const p = disk.properties || {};
  if (chip === 'finding' && !disk.finding) return false;
  if (chip === 'unattached' && p.diskState !== 'Unattached') return false;
  if (chip === 'attached' && p.diskState !== 'Attached') return false;
  if (chip === 'premium' && !String(p.sku || '').includes('Premium')) return false;
  return true;
}

export function sortConceptDisks(disks, sortKey, sortDir) {
  const dir = sortDir === 'asc' ? 1 : -1;
  const sorted = [...disks];
  sorted.sort((a, b) => {
    if (sortKey === 'name') return a.name.localeCompare(b.name) * dir;
    if (sortKey === 'region') return String(a.region).localeCompare(String(b.region)) * dir;
    if (sortKey === 'billed_mtd') return ((a.cost?.billed_mtd || 0) - (b.cost?.billed_mtd || 0)) * dir;
    if (sortKey === 'retail_monthly') return ((a.cost?.retail_monthly || 0) - (b.cost?.retail_monthly || 0)) * dir;
    if (sortKey === 'finding') return ((b.finding ? 1 : 0) - (a.finding ? 1 : 0)) * dir;
    if (sortKey === 'diskSizeGB') return ((a.properties?.diskSizeGB || 0) - (b.properties?.diskSizeGB || 0)) * dir;
    const am = a.metrics?.[sortKey];
    const bm = b.metrics?.[sortKey];
    if (am != null && bm != null) return (am - bm) * dir;
    const av = a.properties?.[sortKey] || '';
    const bv = b.properties?.[sortKey] || '';
    return String(av).localeCompare(String(bv)) * dir;
  });
  return sorted;
}

export function severityLabel(severity) {
  const s = String(severity || '').toLowerCase();
  if (!s) return '—';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Table column definitions — identity + assessment columns + metrics + cost + finding + location. */
export function diskTableColumns() {
  return [
    { key: 'name', label: 'Disk' },
    ...DISK_LIST_COLUMNS.map((col) => ({ key: col.key, label: col.label })),
    ...DISK_LIST_METRICS.map((m) => ({ key: m.factKey, label: m.label })),
    { key: 'billed_mtd', label: 'Billed MTD' },
    { key: 'retail_monthly', label: 'Retail monthly' },
    { key: 'finding', label: 'Finding' },
    { key: 'region', label: DISK_LIST_LOCATION.label },
  ];
}

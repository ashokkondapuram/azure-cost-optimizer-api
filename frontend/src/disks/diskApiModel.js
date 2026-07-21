/**
 * Map live API disk rows → concept v2 inventory record shape.
 *
 * Canonical API contract (list + detail):
 * - assessment_properties / property_rows — EAV assessment fields (diskSizeGB, diskState, …)
 * - properties — merged ARM + assessment (backend may pre-merge; adapter re-merges for safety)
 * - metrics | _metrics | metricsFacts — utilization and monitor facts
 * - cost.{ billed_mtd, retail_monthly, retail_currency, savings_estimate }
 * - finding.{ rule_id, severity, savings, workflow, source }
 *
 * Normalization is defensive: never throws, never drops rows.
 */

import { humanizeAzureRegion } from '../utils/format';
import {
  resourceBilledMtd,
  resourceRetailMonthly,
  resourceRetailCurrency,
  resourceCostBlock,
} from '../utils/costCurrency';
import { resolveResourceFindings } from '../utils/resourceFindingsUtils';
import { normalizeArmId } from '../utils/findingDedupe';

const DISK_INT_PROPS = new Set(['diskSizeGB', 'diskIOPSReadWrite', 'diskMBpsReadWrite']);
const DISK_BOOL_PROPS = new Set(['burstingEnabled', 'optimizedForFrequentAttach', 'supportsHibernation']);

const DISK_METRIC_KEYS = [
  'disk_read_bps',
  'disk_write_bps',
  'disk_read_iops',
  'disk_write_iops',
  'disk_paid_burst_iops',
  'disk_queue_depth',
  'disk_used_pct',
  'disk_iops_utilization_pct',
  'disk_throughput_utilization_pct',
  'peak_disk_iops_utilization_pct',
];

function asPlainObject(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return { ...value };
  }
  return {};
}

function flattenAssessmentProperties(row) {
  const raw = asPlainObject(row?.assessment_properties);
  if (raw.flat && typeof raw.flat === 'object' && !Array.isArray(raw.flat)) {
    return { ...raw.flat };
  }
  const { flat, rows, ...rest } = raw;
  return rest;
}

function coerceDiskPropertyValue(key, val) {
  if (val == null || val === '') return val;
  if (DISK_INT_PROPS.has(key)) {
    const n = Number(val);
    return Number.isFinite(n) ? n : val;
  }
  if (DISK_BOOL_PROPS.has(key)) {
    if (typeof val === 'boolean') return val;
    const s = String(val).toLowerCase();
    if (['yes', 'true', '1'].includes(s)) return true;
    if (['no', 'false', '0'].includes(s)) return false;
  }
  return val;
}

function mergeAssessmentProperties(props, row) {
  const merged = { ...props };
  const assessment = flattenAssessmentProperties(row);
  for (const [key, val] of Object.entries(assessment)) {
    if (val == null || val === '') continue;
    if (merged[key] == null || merged[key] === '') {
      merged[key] = coerceDiskPropertyValue(key, val);
    }
  }
  const propertyRows = row?.property_rows || row?.assessment_property_rows;
  if (Array.isArray(propertyRows)) {
    for (const entry of propertyRows) {
      const key = entry?.property_key;
      const val = entry?.property_value;
      if (!key || val == null || val === '') continue;
      if (merged[key] == null || merged[key] === '') {
        merged[key] = coerceDiskPropertyValue(key, val);
      }
    }
  }
  return merged;
}

function normalizeProperties(row) {
  const props = mergeAssessmentProperties(asPlainObject(row?.properties), row);

  let sku = row?.sku;
  if (typeof sku === 'object' && sku) sku = sku.name || sku.tier;
  if (!sku && props.sku) sku = props.sku;
  if (sku && !props.sku) props.sku = sku;

  if (!props.tier && row?.skuDetails?.tier) props.tier = row.skuDetails.tier;

  if (props.diskState == null && row?.state) {
    const state = String(row.state);
    if (/unattached/i.test(state)) props.diskState = 'Unattached';
    else if (/attached/i.test(state)) props.diskState = 'Attached';
    else props.diskState = state;
  }

  if (props.diskSizeGB == null && row?.skuDetails?.size != null) {
    const size = Number(row.skuDetails.size);
    if (Number.isFinite(size)) props.diskSizeGB = size;
  }

  if (!props.managedBy && props.diskState === 'Unattached') props.managedBy = '—';

  return props;
}

function rowMetrics(row) {
  const metrics = asPlainObject(row?.metrics || row?._metrics);
  const factSources = [row?.metricsFacts, row?._technical_facts];
  for (const facts of factSources) {
    const block = asPlainObject(facts);
    for (const key of DISK_METRIC_KEYS) {
      if (block[key] != null && metrics[key] == null) {
        metrics[key] = block[key];
      }
    }
  }
  return metrics;
}

function resolvedBilledMtd(row, block) {
  const billed = resourceBilledMtd(row);
  const nested = Number(block?.billed_mtd);
  if (Number.isFinite(nested) && nested > 0) return nested;
  return billed;
}

function rowCost(row) {
  const block = resourceCostBlock(row);
  const currency = resourceRetailCurrency(row);
  if (block) {
    return {
      billed_mtd: resolvedBilledMtd(row, block),
      retail_monthly: block.retail_monthly ?? resourceRetailMonthly(row),
      retail_currency: block.retail_currency || currency,
      retail_source: block.retail_source || row?.retailSource || row?.retail_source || null,
      retail_pending: block.retail_pending ?? false,
      savings_estimate: block.savings_estimate ?? row?.analysisSavingsUsd ?? row?.analysis_savings_usd ?? 0,
    };
  }
  return {
    billed_mtd: resourceBilledMtd(row),
    retail_monthly: resourceRetailMonthly(row),
    retail_currency: currency,
    retail_source: row?.retailSource || row?.retail_source || null,
    retail_pending: false,
    savings_estimate: row?.analysisSavingsUsd ?? row?.analysis_savings_usd ?? 0,
  };
}

function rowFinding(row, findingsByResource, options = {}) {
  if (row?.finding && typeof row.finding === 'object') return row.finding;
  const rid = normalizeArmId(row?.id || row?.resource_id);
  const resolved = resolveResourceFindings(row, findingsByResource?.get?.(rid) || [], options);
  const primary = resolved?.[0];
  if (!primary) return null;
  const findingCount = resolved.length;
  return {
    rule_id: primary.rule_id || primary.id,
    severity: String(primary.severity || 'medium').toLowerCase(),
    savings: Number(primary.estimated_savings_usd ?? primary.savings ?? 0) || 0,
    workflow: 'proposed',
    source: primary.source || 'engine',
    evidence: primary.evidence,
    findingCount,
  };
}

function passthroughDiskRow(row) {
  return {
    id: row?.id || row?.resource_id || null,
    name: row?.name || row?.resource_name || '—',
    resourceGroup: row?.resourceGroup || row?.resource_group || '—',
    region: row?.location || row?.region || '—',
    subscription: row?.subscription_id || row?.subscription || null,
    properties: asPlainObject(row?.properties),
    metrics: asPlainObject(row?.metrics || row?._metrics),
    cost: {
      billed_mtd: resourceBilledMtd(row),
      retail_monthly: resourceRetailMonthly(row),
      retail_currency: resourceRetailCurrency(row),
      retail_source: null,
      retail_pending: false,
      savings_estimate: row?.analysisSavingsUsd ?? 0,
    },
    finding: row?.finding && typeof row.finding === 'object' ? row.finding : null,
    case_id: row?.case_id || null,
    tags: asPlainObject(row?.tags),
    assessment_properties: flattenAssessmentProperties(row),
    property_rows: row?.property_rows || row?.assessment_property_rows || [],
    _raw: row,
    _normalizeError: true,
  };
}

/** Normalize one API row to concept v2 disk inventory record. Never returns null/undefined. */
export function normalizeDiskFromApi(row, findingsByResource, options = {}) {
  if (!row || typeof row !== 'object') {
    return passthroughDiskRow(row || {});
  }
  try {
    const props = normalizeProperties(row);
    return {
      id: row.id || row.resource_id || null,
      name: row.name || row.resource_name || '—',
      resourceGroup: row.resourceGroup || row.resource_group || '—',
      region: humanizeAzureRegion(row.location || row.region) || row.location || row.region || '—',
      subscription: row.subscription_id || row.subscription || null,
      properties: props,
      metrics: rowMetrics(row),
      cost: rowCost(row),
      finding: rowFinding(row, findingsByResource, options),
      case_id: row.case_id || null,
      tags: asPlainObject(row.tags),
      assessment_properties: flattenAssessmentProperties(row),
      property_rows: row.property_rows || row.assessment_property_rows || [],
      _raw: row,
    };
  } catch (err) {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.warn('[diskApiModel] normalizeDiskFromApi failed; using passthrough row', err, row);
    }
    return passthroughDiskRow(row);
  }
}

/** @deprecated Use normalizeDiskFromApi — kept for existing imports. */
export const apiRowToConceptDisk = normalizeDiskFromApi;

export function apiRowsToConceptDisks(rows, findingsByResource, options = {}) {
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => row != null)
    .map((row) => normalizeDiskFromApi(row, findingsByResource, options));
}

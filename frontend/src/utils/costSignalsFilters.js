/**
 * Exclude governance / region-approval items from cost-driving signals and metric triggers.
 * Region governance belongs in findings and the governance dashboard — not cost drivers.
 */

const GOVERNANCE_FACT_KEYS = new Set([
  'region_approved',
  'regionapproved',
  'region_classification',
  'regionclassification',
  'recommended_region',
  'recommendedregion',
  'recommendedregiondisplay',
  'current_region',
  'currentregion',
  'region_move_allowed',
  'regionmoveallowed',
  'region_migration_required',
  'regionmigrationrequired',
]);

const GOVERNANCE_LABEL_PATTERN = /region approval|approve region|approved region|unapproved region|region govern|data residency|region migration|recommended region/i;

const GOVERNANCE_RULE_PATTERN = /unapproved_region|region_governance|governance_region|best_unapproved/i;

const GOVERNANCE_ITEM_ID_PATTERN = /region-classification|recommended-region|region-migration|region_approval/i;

export function isGovernanceCostSignal(item) {
  if (!item) return false;

  const factKey = String(item.fact_key || '').toLowerCase();
  const label = String(item.label || '');
  const id = String(item.id || '');
  const rules = (item.rules || []).join(' ');

  if (GOVERNANCE_FACT_KEYS.has(factKey)) return true;
  if (item.kind === 'region') return true;
  if (GOVERNANCE_LABEL_PATTERN.test(label)) return true;
  if (GOVERNANCE_RULE_PATTERN.test(rules)) return true;
  if (GOVERNANCE_ITEM_ID_PATTERN.test(id)) return true;

  return false;
}

export function filterCostDrivingMetrics(metrics = []) {
  return (metrics || []).filter((metric) => !isGovernanceCostSignal(metric));
}

export function filterCostDrivers(drivers = []) {
  return (drivers || []).filter((driver) => !isGovernanceCostSignal(driver));
}

/** Return a metrics bundle safe for the Cost drivers tab (no region/governance rows). */
export function filterMetricsBundleForCostSignals(metricsData) {
  if (!metricsData) return metricsData;

  const mapping = metricsData.cost_driver_mapping;
  return {
    ...metricsData,
    metrics: filterCostDrivingMetrics(metricsData.metrics),
    derived: filterCostDrivingMetrics(metricsData.derived),
    cost_driver_mapping: mapping
      ? {
        ...mapping,
        cost_drivers: filterCostDrivers(mapping.cost_drivers),
      }
      : mapping,
  };
}

export function countCostSignalTriggers(metricsData) {
  if (!metricsData) return 0;
  const filtered = filterMetricsBundleForCostSignals(metricsData);
  if (!filtered) return 0;
  return [...(filtered.metrics || []), ...(filtered.derived || [])].filter((m) => m?.trigger).length;
}

export function countCostDrivers(metricsData) {
  if (!metricsData) return 0;
  const filtered = filterMetricsBundleForCostSignals(metricsData);
  if (!filtered) return 0;
  return filtered.cost_driver_mapping?.cost_drivers?.length || 0;
}

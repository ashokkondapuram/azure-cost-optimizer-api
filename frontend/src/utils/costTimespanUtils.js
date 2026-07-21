/** Dashboard cost period presets mapped to backend timeframe IDs. */

import { COST_TIMEFRAME_OPTIONS, mapTimeframeCatalog } from '../config/costTimeframes';

export const DEFAULT_DASHBOARD_COST_PERIOD = 'Last30Days';

const DASHBOARD_PERIOD_IDS = [
  'Last7Days',
  'Last14Days',
  'Last30Days',
  'Last60Days',
  'Last90Days',
  'WeekToDate',
  'MonthToDate',
  'TheLastMonth',
  'ThisQuarter',
  'Last3Months',
  'Last6Months',
  'Last12Months',
  'ThisYear',
];

export const DASHBOARD_COST_PERIOD_OPTIONS = DASHBOARD_PERIOD_IDS.map((value) => {
  const match = COST_TIMEFRAME_OPTIONS.find((opt) => opt.value === value);
  return {
    value,
    label: match?.label || value,
    compareDays: 7,
  };
});

export function dashboardCostPeriodOptionsFromCatalog(catalog = []) {
  const mapped = mapTimeframeCatalog(catalog);
  const byId = Object.fromEntries(mapped.map((opt) => [opt.value, opt]));
  return DASHBOARD_PERIOD_IDS
    .filter((id) => byId[id])
    .map((id) => ({
      value: id,
      label: byId[id].label,
      compareDays: 7,
    }));
}

export function dashboardCostPeriodLabel(value, options = DASHBOARD_COST_PERIOD_OPTIONS) {
  const match = options.find((option) => option.value === value);
  return match?.label || value || DEFAULT_DASHBOARD_COST_PERIOD;
}

export function isValidDashboardCostPeriod(value, options = DASHBOARD_COST_PERIOD_OPTIONS) {
  return options.some((option) => option.value === value);
}

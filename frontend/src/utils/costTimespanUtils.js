/** Dashboard cost period presets mapped to backend timeframe IDs. */

export const DEFAULT_DASHBOARD_COST_PERIOD = 'Last30Days';

export const DASHBOARD_COST_PERIOD_OPTIONS = [
  { value: 'Last7Days', label: 'Last 7 days', compareDays: 7 },
  { value: 'Last30Days', label: 'Last 30 days', compareDays: 7 },
  { value: 'MonthToDate', label: 'This month', compareDays: 7 },
  { value: 'TheLastMonth', label: 'Last month', compareDays: 7 },
];

export function dashboardCostPeriodLabel(value) {
  const match = DASHBOARD_COST_PERIOD_OPTIONS.find((option) => option.value === value);
  return match?.label || value || DEFAULT_DASHBOARD_COST_PERIOD;
}

export function isValidDashboardCostPeriod(value) {
  return DASHBOARD_COST_PERIOD_OPTIONS.some((option) => option.value === value);
}

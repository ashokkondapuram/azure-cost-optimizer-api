/** Cost explorer timeframe presets (mirrors GET /costs/timeframes). */

export const COST_TIMEFRAME_OPTIONS = [
  { value: 'Last7Days', label: 'Last 7 days', group: 'rolling' },
  { value: 'Last14Days', label: 'Last 14 days', group: 'rolling' },
  { value: 'Last30Days', label: 'Last 30 days', group: 'rolling' },
  { value: 'Last60Days', label: 'Last 60 days', group: 'rolling' },
  { value: 'Last90Days', label: 'Last 90 days', group: 'rolling' },
  { value: 'WeekToDate', label: 'Week to date', group: 'rolling' },
  { value: 'MonthToDate', label: 'This month', group: 'calendar' },
  { value: 'BillingMonthToDate', label: 'Billing month to date', group: 'calendar' },
  { value: 'TheLastMonth', label: 'Last month', group: 'calendar' },
  { value: 'ThisQuarter', label: 'This quarter', group: 'calendar' },
  { value: 'LastQuarter', label: 'Last quarter', group: 'calendar' },
  { value: 'Last3Months', label: 'Last 3 months', group: 'rolling' },
  { value: 'Last6Months', label: 'Last 6 months', group: 'rolling' },
  { value: 'Last12Months', label: 'Last 12 months', group: 'rolling' },
  { value: 'ThisYear', label: 'This year', group: 'calendar' },
  { value: 'Custom', label: 'Custom range', group: 'custom', requiresDates: true },
];

export function mapTimeframeCatalog(catalog = []) {
  return catalog.map((item) => ({
    value: item.id,
    label: item.label,
    group: item.group,
    requiresDates: Boolean(item.requires_dates || item.id === 'Custom'),
  }));
}

export const COST_TIMEFRAME_LABELS = Object.fromEntries(
  COST_TIMEFRAME_OPTIONS.map((opt) => [opt.value, opt.label]),
);

export function costTimeframeLabel(value, options = COST_TIMEFRAME_OPTIONS) {
  const match = options.find((opt) => opt.value === value);
  return match?.label || COST_TIMEFRAME_LABELS[value] || value || 'Period';
}

export function buildCostQueryParams({ subscription_id, timeframe, from_date, to_date, ...rest }) {
  const params = { subscription_id, timeframe, ...rest };
  if (timeframe === 'Custom') {
    if (from_date) params.from_date = from_date;
    if (to_date) params.to_date = to_date;
  }
  return params;
}

/** Suggested comparison period when overlaying spend trends. */
export const COMPARE_TIMEFRAME_DEFAULTS = {
  MonthToDate: 'TheLastMonth',
  BillingMonthToDate: 'TheLastMonth',
  Last7Days: 'Custom',
  Last14Days: 'Custom',
  Last30Days: 'TheLastMonth',
  Last60Days: 'Last30Days',
  Last90Days: 'Last3Months',
  WeekToDate: 'Last7Days',
  TheLastMonth: 'Last30Days',
  ThisQuarter: 'LastQuarter',
  LastQuarter: 'Last6Months',
  Last3Months: 'Last6Months',
  Last6Months: 'Last12Months',
  Last12Months: 'ThisYear',
  ThisYear: 'Last12Months',
};

export function defaultCompareTimeframe(timeframe) {
  return COMPARE_TIMEFRAME_DEFAULTS[timeframe] || 'TheLastMonth';
}

export function previousCustomRange(fromDate, toDate) {
  if (!fromDate || !toDate) return null;
  const start = new Date(`${fromDate}T00:00:00`);
  const end = new Date(`${toDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  const dayMs = 86400000;
  const days = Math.max(1, Math.round((end - start) / dayMs) + 1);
  const prevEnd = new Date(start.getTime() - dayMs);
  const prevStart = new Date(prevEnd.getTime() - (days - 1) * dayMs);
  const fmt = (d) => d.toISOString().slice(0, 10);
  return { from_date: fmt(prevStart), to_date: fmt(prevEnd) };
}

/** Cost explorer timeframe presets (mirrors GET /costs/timeframes). */

export const COST_TIMEFRAME_OPTIONS = [
  { value: 'Last7Days', label: 'Last 7 days' },
  { value: 'Last30Days', label: 'Last 30 days' },
  { value: 'MonthToDate', label: 'This month' },
  { value: 'BillingMonthToDate', label: 'Billing month to date' },
  { value: 'TheLastMonth', label: 'Last month' },
  { value: 'ThisQuarter', label: 'This quarter' },
  { value: 'LastQuarter', label: 'Last quarter' },
  { value: 'Last3Months', label: 'Last 3 months' },
  { value: 'Last6Months', label: 'Last 6 months' },
  { value: 'Last12Months', label: 'Last 12 months' },
  { value: 'ThisYear', label: 'This year' },
  { value: 'Custom', label: 'Custom range', requiresDates: true },
];

export const COST_TIMEFRAME_LABELS = Object.fromEntries(
  COST_TIMEFRAME_OPTIONS.map((opt) => [opt.value, opt.label]),
);

export function costTimeframeLabel(value) {
  return COST_TIMEFRAME_LABELS[value] || value || 'Period';
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
  Last30Days: 'TheLastMonth',
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

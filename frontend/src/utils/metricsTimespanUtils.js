/** Azure Monitor ISO 8601 duration options for resource metric lookback. */

export const DEFAULT_METRIC_TIMESPAN = 'P7D';

export const METRIC_TIMESPAN_OPTIONS = [
  { value: 'P1D', label: 'Last 24 hours' },
  { value: 'P7D', label: 'Last 7 days' },
  { value: 'P14D', label: 'Last 14 days' },
  { value: 'P30D', label: 'Last 30 days' },
  { value: 'P90D', label: 'Last 90 days' },
];

export function metricTimespanLabel(value) {
  const match = METRIC_TIMESPAN_OPTIONS.find((option) => option.value === value);
  return match?.label || value || DEFAULT_METRIC_TIMESPAN;
}

export function isValidMetricTimespan(value) {
  return METRIC_TIMESPAN_OPTIONS.some((option) => option.value === value);
}

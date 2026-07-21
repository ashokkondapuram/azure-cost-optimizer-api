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

/** Coerce persisted or API values to a supported Azure Monitor timespan code. */
export function coerceMetricTimespan(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed || trimmed === '[object Object]') {
      return DEFAULT_METRIC_TIMESPAN;
    }
    if (isValidMetricTimespan(trimmed)) {
      return trimmed;
    }
    if (trimmed.startsWith('{')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed === 'object') {
          return coerceMetricTimespan(parsed);
        }
      } catch {
        // ignore malformed JSON blobs from legacy storage
      }
    }
    const upper = trimmed.toUpperCase();
    if (isValidMetricTimespan(upper)) {
      return upper;
    }
    return DEFAULT_METRIC_TIMESPAN;
  }
  if (value && typeof value === 'object') {
    const nested = value.value ?? value.timespan ?? value.id;
    if (typeof nested === 'string' && isValidMetricTimespan(nested)) {
      return nested;
    }
  }
  return DEFAULT_METRIC_TIMESPAN;
}

import { useCallback, useEffect } from 'react';
import usePersistedState from './usePersistedState';
import { coerceMetricTimespan, DEFAULT_METRIC_TIMESPAN } from '../utils/metricsTimespanUtils';

/** Persist Azure Monitor lookback period (P1D, P7D, …) in localStorage. */
export default function usePersistedMetricTimespan(storageKey) {
  const [rawTimespan, setTimespan] = usePersistedState(storageKey, DEFAULT_METRIC_TIMESPAN);
  const timespan = coerceMetricTimespan(rawTimespan);

  // Rewrite legacy object-shaped values (e.g. { value, label }) as plain ISO codes.
  useEffect(() => {
    if (rawTimespan !== timespan) {
      setTimespan(timespan);
    }
  }, [rawTimespan, timespan, setTimespan]);

  const onTimespanChange = useCallback((value) => {
    setTimespan(coerceMetricTimespan(value));
  }, [setTimespan]);
  return [timespan, onTimespanChange];
}

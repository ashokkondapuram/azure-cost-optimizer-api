import { useCallback } from 'react';
import usePersistedState from './usePersistedState';
import { DEFAULT_METRIC_TIMESPAN, isValidMetricTimespan } from '../utils/metricsTimespanUtils';

/** Persist Azure Monitor lookback period (P1D, P7D, …) in localStorage. */
export default function usePersistedMetricTimespan(storageKey) {
  const [timespan, setTimespan] = usePersistedState(storageKey, DEFAULT_METRIC_TIMESPAN);
  const onTimespanChange = useCallback((value) => {
    setTimespan(isValidMetricTimespan(value) ? value : DEFAULT_METRIC_TIMESPAN);
  }, [setTimespan]);
  return [timespan, onTimespanChange];
}

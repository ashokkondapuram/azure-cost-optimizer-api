import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchDailyAnomalies, fetchServiceAnomalies } from '../api/anomalies';

function useDebouncedValue(value, delayMs = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

/**
 * Hook that fetches both daily and service anomaly data for a subscription.
 * Params are debounced to avoid refetching on every slider tick.
 */
export function useAnomalyData(subscriptionId, params = {}) {
  const debounced = useDebouncedValue(params, 400);
  const [daily, setDaily] = useState(null);
  const [service, setService] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    if (!subscriptionId) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const query = {
        window_days: debounced.window_days ?? 30,
        lookback_days: debounced.lookback_days ?? 7,
        threshold_sigma: debounced.threshold_sigma ?? 2.0,
      };
      const [d, s] = await Promise.all([
        fetchDailyAnomalies(subscriptionId, query),
        fetchServiceAnomalies(subscriptionId, query),
      ]);
      if (id !== requestId.current) return;
      setDaily(d);
      setService(s);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [
    subscriptionId,
    debounced.window_days,
    debounced.lookback_days,
    debounced.threshold_sigma,
  ]);

  useEffect(() => { load(); }, [load]);

  return { daily, service, loading, error, refetch: load, params: debounced };
}

import { useState, useEffect, useCallback } from 'react';
import { fetchDailyAnomalies, fetchServiceAnomalies } from '../api/anomalies';

/**
 * Hook that fetches both daily and service anomaly data for a subscription.
 * Returns { daily, service, loading, error, refetch }.
 */
export function useAnomalyData(subscriptionId, dailyParams = {}, serviceParams = {}) {
  const [daily, setDaily] = useState(null);
  const [service, setService] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!subscriptionId) return;
    setLoading(true);
    setError(null);
    try {
      const [d, s] = await Promise.all([
        fetchDailyAnomalies(subscriptionId, dailyParams),
        fetchServiceAnomalies(subscriptionId, serviceParams),
      ]);
      setDaily(d);
      setService(s);
    } catch (err) {
      setError(err.message || 'Failed to load anomaly data');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscriptionId, dailyParams.window_days, dailyParams.threshold_sigma, dailyParams.lookback_days]);

  useEffect(() => { load(); }, [load]);

  return { daily, service, loading, error, refetch: load };
}

import { useQuery } from '@tanstack/react-query';
import { fetchDrawerResourceBundle } from '../utils/batchedQueries';
import { coerceMetricTimespan } from '../utils/metricsTimespanUtils';

/** Combined metrics + advanced analysis for the resource insight drawer. */
export default function useDrawerResourceBundle({
  subscriptionId,
  resourceId,
  timespan,
  enabled = true,
}) {
  const normalizedTimespan = coerceMetricTimespan(timespan);
  return useQuery({
    queryKey: ['drawer-resource-bundle', subscriptionId, resourceId, normalizedTimespan],
    queryFn: ({ signal }) => fetchDrawerResourceBundle({
      subscriptionId,
      resourceId,
      timespan: normalizedTimespan,
      includeMetrics: true,
      includeAdvancedAnalysis: true,
      signal,
    }),
    enabled: enabled && !!subscriptionId && !!resourceId && !!normalizedTimespan,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

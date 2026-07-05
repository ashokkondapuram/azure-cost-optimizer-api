import { useQuery } from '@tanstack/react-query';
import { fetchDrawerResourceBundle } from '../utils/batchedQueries';

/** Combined metrics + advanced analysis for the resource insight drawer. */
export default function useDrawerResourceBundle({
  subscriptionId,
  resourceId,
  timespan,
  enabled = true,
}) {
  return useQuery({
    queryKey: ['drawer-resource-bundle', subscriptionId, resourceId, timespan],
    queryFn: ({ signal }) => fetchDrawerResourceBundle({
      subscriptionId,
      resourceId,
      timespan,
      includeMetrics: true,
      includeAdvancedAnalysis: true,
      signal,
    }),
    enabled: enabled && !!subscriptionId && !!resourceId && !!timespan,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

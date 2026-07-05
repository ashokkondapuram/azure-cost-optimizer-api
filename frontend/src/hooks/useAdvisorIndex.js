import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchAzureAdvisorRecommendations } from '../api/azure';
import {
  ADVISOR_INDEX_MAX,
  fetchAllAzureAdvisorRecommendations,
  indexAdvisorByResourceId,
} from '../utils/advisorUtils';

/** Map resource_id (lowercase) → Azure Advisor recommendations for the subscription. */
export default function useAdvisorIndex(subscription) {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['advisor-index', subscription],
    queryFn: () => fetchAllAzureAdvisorRecommendations(
      fetchAzureAdvisorRecommendations,
      subscription,
    ),
    enabled: !!subscription,
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const items = data?.items || [];
  const indexReady = !!subscription && !isLoading && !isError;
  const truncated = (data?.total || items.length) > ADVISOR_INDEX_MAX;

  const byResourceId = useMemo(
    () => indexAdvisorByResourceId(items),
    [items],
  );

  const savingsByResource = useMemo(() => {
    const map = new Map();
    for (const [rid, recs] of byResourceId) {
      map.set(
        rid,
        recs.reduce((sum, rec) => sum + (rec.potential_savings_monthly || 0), 0),
      );
    }
    return map;
  }, [byResourceId]);

  return {
    items,
    byResourceId,
    savingsByResource,
    total: data?.total ?? items.length,
    isLoading,
    isError,
    error,
    refetch,
    indexReady,
    truncated,
    hasData: items.length > 0,
  };
}

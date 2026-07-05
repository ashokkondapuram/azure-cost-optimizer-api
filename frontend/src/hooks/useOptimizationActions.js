import { useQuery } from '@tanstack/react-query';
import { fetchOptimizationActions } from '../api/azure';
import { ACTION_INDEX_LIMIT } from '../utils/actionUtils';

export default function useOptimizationActions(subscription, filters = {}) {
  const enabled = Boolean(subscription);

  const query = useQuery({
    queryKey: ['optimization-actions', subscription, filters],
    queryFn: () => fetchOptimizationActions({
      subscription_id: subscription,
      limit: ACTION_INDEX_LIMIT,
      ...filters,
    }),
    enabled,
    staleTime: 60_000,
  });

  const items = query.data?.items || [];
  const summary = query.data?.summary || {};
  const byId = new Map(items.map((item) => [item.id, item]));

  return {
    ...query,
    items,
    summary,
    byId,
    total: query.data?.total ?? items.length,
    totalSavings: query.data?.total_estimated_monthly_savings ?? 0,
    pageSavings: query.data?.page_estimated_monthly_savings ?? 0,
    indexReady: !query.isLoading && (query.isSuccess || query.isError),
  };
}

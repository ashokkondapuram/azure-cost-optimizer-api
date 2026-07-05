import { useQuery } from '@tanstack/react-query';
import { fetchOptimizationScoreboard } from '../api/azure';
import { SCOREBOARD_LIMIT } from '../utils/scoreboardUtils';

export default function useOptimizationScoreboard(subscription, filters = {}) {
  const enabled = Boolean(subscription);

  const query = useQuery({
    queryKey: ['optimization-scoreboard', subscription, filters],
    queryFn: () => fetchOptimizationScoreboard({
      subscription_id: subscription,
      limit: SCOREBOARD_LIMIT,
      ...filters,
    }),
    enabled,
    staleTime: 60_000,
  });

  const items = query.data?.items || [];
  const tierSummary = query.data?.tier_summary || {};

  return {
    ...query,
    items,
    tierSummary,
    total: query.data?.total ?? items.length,
    evaluationDate: query.data?.evaluation_date,
    totalSavings: query.data?.total_estimated_monthly_savings ?? 0,
    indexReady: !query.isLoading && (query.isSuccess || query.isError),
  };
}

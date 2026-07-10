import { fetchOptimizationScoreboard } from '../api/azure';
import { SCOREBOARD_PAGE_SIZE } from '../utils/scoreboardUtils';
import { useInfiniteOptimizationList, useOptimizationListPage } from './useInfiniteOptimizationList';

export default function useOptimizationScoreboard(subscription, filters = {}, options = {}) {
  const infinite = options.infinite !== false;
  const pageSize = options.pageSize ?? SCOREBOARD_PAGE_SIZE;

  const infiniteQuery = useInfiniteOptimizationList({
    queryKey: ['optimization-scoreboard'],
    queryFn: fetchOptimizationScoreboard,
    subscription,
    filters,
    pageSize,
    enabled: infinite && Boolean(subscription),
  });

  const pageQuery = useOptimizationListPage({
    queryKey: ['optimization-scoreboard'],
    queryFn: fetchOptimizationScoreboard,
    subscription,
    filters,
    limit: options.limit ?? pageSize,
    enabled: !infinite && Boolean(subscription),
  });

  const query = infinite ? infiniteQuery : pageQuery;
  const firstPage = infinite ? infiniteQuery.firstPage : pageQuery.firstPage;

  return {
    ...query,
    tierSummary: firstPage?.tier_summary || {},
    evaluationDate: firstPage?.evaluation_date,
    totalSavings: firstPage?.distinct_estimated_monthly_savings
      ?? firstPage?.total_estimated_monthly_savings
      ?? 0,
    pageSavings: firstPage?.distinct_page_estimated_monthly_savings
      ?? firstPage?.page_estimated_monthly_savings
      ?? 0,
    loadMore: infinite ? infiniteQuery.loadMore : undefined,
    hasMore: infinite ? infiniteQuery.hasMore : false,
    isLoadingMore: infinite ? infiniteQuery.isLoadingMore : false,
    loadedCount: query.items.length,
  };
}

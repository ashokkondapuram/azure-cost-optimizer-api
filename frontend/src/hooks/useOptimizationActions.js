import { fetchOptimizationActions } from '../api/azure';
import { ACTION_PAGE_SIZE } from '../utils/actionUtils';
import { useInfiniteOptimizationList, useOptimizationListPage } from './useInfiniteOptimizationList';

export default function useOptimizationActions(subscription, filters = {}, options = {}) {
  const infinite = options.infinite !== false;
  const pageSize = options.pageSize ?? ACTION_PAGE_SIZE;

  const infiniteQuery = useInfiniteOptimizationList({
    queryKey: ['optimization-actions'],
    queryFn: fetchOptimizationActions,
    subscription,
    filters,
    pageSize,
    enabled: infinite && Boolean(subscription),
  });

  const pageQuery = useOptimizationListPage({
    queryKey: ['optimization-actions'],
    queryFn: fetchOptimizationActions,
    subscription,
    filters,
    limit: options.limit ?? pageSize,
    enabled: !infinite && Boolean(subscription),
  });

  const query = infinite ? infiniteQuery : pageQuery;
  const firstPage = infinite ? infiniteQuery.firstPage : pageQuery.firstPage;
  const items = query.items;
  const summary = firstPage?.summary || {};
  const byId = new Map(items.map((item) => [item.id, item]));

  return {
    ...query,
    items,
    summary,
    byId,
    total: query.total,
    totalSavings: firstPage?.distinct_estimated_monthly_savings
      ?? firstPage?.total_estimated_monthly_savings
      ?? 0,
    pageSavings: firstPage?.distinct_page_estimated_monthly_savings
      ?? firstPage?.page_estimated_monthly_savings
      ?? 0,
    loadMore: infinite ? infiniteQuery.loadMore : undefined,
    hasMore: infinite ? infiniteQuery.hasMore : false,
    isLoadingMore: infinite ? infiniteQuery.isLoadingMore : false,
    loadedCount: items.length,
  };
}

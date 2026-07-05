import { useInfiniteQuery } from '@tanstack/react-query';
import { fetchResources } from '../api/azure';
import { DEFAULT_RESOURCE_PAGE_SIZE } from '../utils/syncScope';

/**
 * Incremental DB list loading — first page on mount; more pages via loadMore.
 */
export default function usePaginatedResources({
  apiPath,
  subscription,
  dataSource = 'db',
  pageSize = DEFAULT_RESOURCE_PAGE_SIZE,
  enabled = true,
  includeProperties = false,
}) {
  const query = useInfiniteQuery({
    queryKey: [apiPath, subscription, dataSource, 'paged', pageSize, includeProperties],
    enabled: Boolean(enabled && subscription),
    staleTime: dataSource === 'db' ? 5 * 60_000 : 0,
    initialPageParam: 0,
    queryFn: ({ pageParam }) => fetchResources(apiPath, {
      subscription_id: subscription,
      source: dataSource,
      limit: pageSize,
      offset: pageParam,
      include_properties: includeProperties,
    }),
    getNextPageParam: (lastPage) => (
      lastPage?.has_more ? (lastPage.offset + lastPage.items.length) : undefined
    ),
  });

  const pages = query.data?.pages || [];
  const items = pages.flatMap((p) => p.items || []);
  const total = pages[0]?.total ?? items.length;

  return {
    ...query,
    items,
    total,
    hasMore: Boolean(query.hasNextPage),
    loadMore: query.fetchNextPage,
    isLoadingMore: query.isFetchingNextPage,
  };
}

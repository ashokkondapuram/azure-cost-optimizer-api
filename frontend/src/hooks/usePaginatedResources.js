import { useInfiniteQuery } from '@tanstack/react-query';
import { fetchResources } from '../api/azure';
import { DEFAULT_RESOURCE_PAGE_SIZE } from '../utils/syncScope';

/**
 * Incremental DB list loading — first page on mount; more pages via loadMore.
 * Uses keyset cursor when the API returns next_cursor (falls back to offset).
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
    initialPageParam: { offset: 0, cursor: null },
    queryFn: ({ pageParam }) => {
      const params = {
        subscription_id: subscription,
        source: dataSource,
        limit: pageSize,
        include_properties: includeProperties,
      };
      if (pageParam?.cursor) {
        params.cursor = pageParam.cursor;
        params.offset = pageParam.offset ?? 0;
      } else {
        params.offset = pageParam?.offset ?? 0;
      }
      return fetchResources(apiPath, params);
    },
    getNextPageParam: (lastPage, _pages, lastPageParam) => {
      if (!lastPage?.has_more || (lastPage.total ?? 0) <= 0) return undefined;
      const pageCount = Number(lastPage.page_count ?? lastPage.items?.length ?? 0);
      const step = pageCount > 0 ? pageCount : (lastPage.limit || pageSize);
      const nextOffset = (lastPageParam?.offset ?? lastPage.offset ?? 0) + step;
      if (lastPage.next_cursor) {
        return { cursor: lastPage.next_cursor, offset: nextOffset };
      }
      if (nextOffset <= (lastPage.offset ?? 0)) return undefined;
      return { offset: nextOffset, cursor: null };
    },
    maxPages: 40,
  });

  const pages = query.data?.pages || [];
  const items = pages.flatMap((p) => p.items || []);
  const total = pages[0]?.total ?? items.length;
  const hasMore = Boolean(query.hasNextPage) && total > 0;

  return {
    ...query,
    items,
    total,
    hasMore,
    loadMore: query.fetchNextPage,
    isLoadingMore: query.isFetchingNextPage,
  };
}

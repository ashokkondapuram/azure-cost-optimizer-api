import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

/**
 * Offset-based infinite list for optimization hub tables.
 */
export function useInfiniteOptimizationList({
  queryKey,
  queryFn,
  subscription,
  filters = {},
  pageSize = 50,
  enabled = true,
  staleTime = 60_000,
}) {
  const query = useInfiniteQuery({
    queryKey: [...queryKey, subscription, filters, pageSize, 'infinite'],
    enabled: Boolean(enabled && subscription),
    staleTime,
    initialPageParam: 0,
    queryFn: ({ pageParam: offset }) => queryFn({
      subscription_id: subscription,
      limit: pageSize,
      offset,
      ...filters,
    }),
    getNextPageParam: (lastPage) => {
      const loaded = (lastPage?.offset ?? 0) + (lastPage?.count ?? lastPage?.items?.length ?? 0);
      const total = lastPage?.total ?? 0;
      if (lastPage?.has_more === false) return undefined;
      if (loaded >= total) return undefined;
      return loaded;
    },
  });

  const pages = query.data?.pages || [];
  const firstPage = pages[0];
  const items = pages.flatMap((page) => page?.items || []);
  const total = firstPage?.total ?? items.length;
  const hasMore = Boolean(query.hasNextPage) && total > items.length;

  return {
    ...query,
    items,
    total,
    hasMore,
    loadMore: query.fetchNextPage,
    isLoadingMore: query.isFetchingNextPage,
    firstPage,
    indexReady: !query.isLoading && (query.isSuccess || query.isError),
  };
}

/**
 * Single-page fetch (overview previews, subscription summaries).
 */
export function useOptimizationListPage({
  queryKey,
  queryFn,
  subscription,
  filters = {},
  limit = 50,
  enabled = true,
  staleTime = 60_000,
}) {
  const query = useQuery({
    queryKey: [...queryKey, subscription, filters, limit, 'page'],
    queryFn: () => queryFn({
      subscription_id: subscription,
      limit,
      offset: 0,
      ...filters,
    }),
    enabled: Boolean(enabled && subscription),
    staleTime,
  });

  const items = query.data?.items || [];

  return {
    ...query,
    items,
    total: query.data?.total ?? items.length,
    indexReady: !query.isLoading && (query.isSuccess || query.isError),
    firstPage: query.data,
  };
}

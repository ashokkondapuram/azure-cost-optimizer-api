import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchResourceDailyCost } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { useAuth } from '../context/AuthContext';
import {
  hasAttemptedDrawerCostSync,
  markDrawerCostSyncAttempted,
} from '../utils/drawerCostSyncSession';
import {
  shouldAutoSyncDrawerCost,
  triggerDrawerCostSync,
} from '../utils/drawerCostSyncTrigger';
import {
  buildResourceSpendTrendChart,
  hasSpendTrendData,
} from '../utils/drawerResourceCostTrend';

const DAILY_COST_QUERY_KEY = 'drawer-resource-daily-cost';

export function drawerResourceDailyCostQueryKey(subscriptionId, resourceId) {
  return [DAILY_COST_QUERY_KEY, subscriptionId, resourceId];
}

export default function useDrawerResourceCostTrend({
  subscriptionId,
  resourceId,
  enabled = true,
  days = 28,
}) {
  const queryClient = useQueryClient();
  const { isAdmin } = useAuth();
  const [syncState, setSyncState] = useState('idle');
  const [syncError, setSyncError] = useState(null);
  const [syncFinished, setSyncFinished] = useState(false);
  const syncAbortRef = useRef(null);

  const query = useQuery({
    queryKey: drawerResourceDailyCostQueryKey(subscriptionId, resourceId),
    queryFn: ({ signal }) => fetchResourceDailyCost({
      subscription_id: subscriptionId,
      resource_id: resourceId,
      days,
    }, { signal }),
    enabled: enabled && Boolean(subscriptionId && resourceId),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const { refetch } = query;

  const chartData = useMemo(
    () => buildResourceSpendTrendChart(query.data?.points),
    [query.data?.points],
  );
  const hasChart = hasSpendTrendData(chartData);

  useEffect(() => () => {
    syncAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!enabled || !subscriptionId || !resourceId) return undefined;
    if (query.isLoading || query.isFetching) return undefined;
    if (!query.data || hasChart) {
      if (hasChart) {
        setSyncState('idle');
        setSyncError(null);
      }
      return undefined;
    }

    const sessionAttempted = hasAttemptedDrawerCostSync(subscriptionId);
    if (!shouldAutoSyncDrawerCost({
      enabled,
      subscriptionId,
      resourceId,
      isLoading: query.isLoading,
      dailyPayload: query.data,
      sessionAttempted,
    })) {
      return undefined;
    }

    markDrawerCostSyncAttempted(subscriptionId);
    syncAbortRef.current?.abort();
    const controller = new AbortController();
    syncAbortRef.current = controller;

    setSyncState('syncing');
    setSyncError(null);
    setSyncFinished(false);

    (async () => {
      try {
        await triggerDrawerCostSync({
          subscriptionId,
          isAdmin,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;

        await queryClient.invalidateQueries({
          queryKey: drawerResourceDailyCostQueryKey(subscriptionId, resourceId),
        });
        await refetch();
        setSyncFinished(true);
        setSyncState('idle');
      } catch (err) {
        if (controller.signal.aborted) return;
        setSyncState('error');
        setSyncError(getErrorMessage(err, 'Could not sync spend history. Try again from Cost explorer.'));
      }
    })();

    return () => {
      controller.abort();
    };
  }, [
    enabled,
    subscriptionId,
    resourceId,
    query.data,
    query.isLoading,
    query.isFetching,
    hasChart,
    isAdmin,
    queryClient,
    refetch,
  ]);

  return {
    dailyPayload: query.data,
    chartData,
    hasChart,
    isLoading: query.isLoading,
    isSyncing: syncState === 'syncing',
    syncError,
    syncFinished,
    queryError: query.error,
    refetch,
  };
}

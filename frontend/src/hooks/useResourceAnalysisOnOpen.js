import { useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { analyzeResource, fetchResourceAzureMetrics } from '../api/azure';
import { normalizeArmId } from '../utils/findingDedupe';

/** Fetch Azure Monitor metrics, then run scoped optimization analysis when a drawer opens. */
export default function useResourceAnalysisOnOpen({ subscriptionId, resourceId, enabled = true }) {
  const queryClient = useQueryClient();
  const lastTriggered = useRef('');

  const { mutate } = useMutation({
    mutationFn: async () => {
      const rid = normalizeArmId(resourceId);
      if (rid) {
        try {
          await fetchResourceAzureMetrics({ resource_id: rid, timespan: 'P30D' });
        } catch {
          // Analysis still runs with cached or freshly fetched monitor data on the server.
        }
      }
      return analyzeResource({
        subscription_id: subscriptionId,
        resource_id: resourceId,
      });
    },
    onSuccess: () => {
      if (!subscriptionId) return;
      queryClient.invalidateQueries({ queryKey: ['findings-index', subscriptionId] });
      queryClient.invalidateQueries({ queryKey: ['findings-summary', subscriptionId] });
      if (resourceId) {
        queryClient.invalidateQueries({
          queryKey: ['drawer-resource-bundle', subscriptionId, normalizeArmId(resourceId)],
        });
      }
    },
  });

  const mutateRef = useRef(mutate);
  mutateRef.current = mutate;

  useEffect(() => {
    const rid = normalizeArmId(resourceId);
    if (!enabled || !subscriptionId || !rid) return;
    const key = `${subscriptionId}:${rid}`;
    if (lastTriggered.current === key) return;
    lastTriggered.current = key;
    mutateRef.current();
  }, [enabled, subscriptionId, resourceId]);
}

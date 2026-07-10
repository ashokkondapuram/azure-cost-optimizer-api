import { useQuery } from '@tanstack/react-query';
import { fetchRolloutStages } from '../api/azure';

export default function useRolloutStages(subscription, filters = {}) {
  const enabled = Boolean(subscription);

  const query = useQuery({
    queryKey: ['rollout-stages', subscription, filters],
    queryFn: () => fetchRolloutStages({ subscription_id: subscription, ...filters }),
    enabled,
    staleTime: 30_000,
  });

  return {
    ...query,
    items: query.data?.items || [],
    statusSummary: query.data?.status_summary || {},
    total: query.data?.count ?? 0,
    indexReady: !query.isLoading && (query.isSuccess || query.isError),
  };
}

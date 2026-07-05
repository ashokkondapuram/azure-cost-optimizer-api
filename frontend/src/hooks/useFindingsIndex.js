import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchFindings } from '../api/azure';
import { dedupeOpenFindings, normalizeArmId } from '../utils/findingDedupe';

export const FINDINGS_INDEX_LIMIT = 2000;

/** Map resource_id (lowercase) → open findings for the subscription. */
export default function useFindingsIndex(subscription) {
  const {
    data: rawFindings = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['findings-index', subscription],
    queryFn: () => fetchFindings({
      subscription_id: subscription,
      status: 'open',
      limit: FINDINGS_INDEX_LIMIT,
    }),
    enabled: !!subscription,
    staleTime: 2 * 60_000,
  });

  const findings = useMemo(
    () => dedupeOpenFindings(rawFindings),
    [rawFindings],
  );

  const indexReady = !!subscription && !isLoading && !isError;
  const truncated = findings.length >= FINDINGS_INDEX_LIMIT;

  const byResourceId = useMemo(() => {
    const map = new Map();
    for (const f of findings) {
      const key = normalizeArmId(f.resource_id);
      if (!key) continue;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(f);
    }
    return map;
  }, [findings]);

  const savingsByResource = useMemo(() => {
    const map = new Map();
    for (const [rid, list] of byResourceId) {
      map.set(rid, list.reduce((s, f) => s + (f.estimated_savings_usd || 0), 0));
    }
    return map;
  }, [byResourceId]);

  return {
    findings,
    byResourceId,
    savingsByResource,
    isLoading,
    isError,
    error,
    indexReady,
    truncated,
  };
}

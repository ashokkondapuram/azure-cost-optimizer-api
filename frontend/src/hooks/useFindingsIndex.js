import { useMemo } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { fetchFindingsSummary } from '../api/azure';
import { dedupeOpenFindings, normalizeArmId } from '../utils/findingDedupe';
import { expandFindingRecommendations } from '../utils/findingAggregation';
import { buildSavingsByResourceMap } from '../utils/unifiedSavings';
import { sortFindingsByPriority } from '../utils/taxonomy';
import { fetchAllOpenFindings } from '../utils/findingsUtils';

export const FINDINGS_INDEX_LIMIT = 2000;

/** Map resource_id (lowercase) → open findings for the subscription. */
export default function useFindingsIndex(subscription, { inventoryOnly = false } = {}) {
  const {
    data: pageData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['findings-index', subscription, inventoryOnly ? 'inventory' : 'all'],
    queryFn: () => fetchAllOpenFindings(subscription, { inventoryOnly }),
    enabled: !!subscription,
    staleTime: 2 * 60_000,
    placeholderData: keepPreviousData,
  });

  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
    error: summaryErrorDetail,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['findings-summary', subscription, inventoryOnly ? 'inventory' : 'all'],
    queryFn: () => fetchFindingsSummary({
      subscription_id: subscription,
      ...(inventoryOnly ? { inventory_only: true } : {}),
    }),
    enabled: !!subscription,
    staleTime: 2 * 60_000,
    placeholderData: keepPreviousData,
  });

  const rawFindings = pageData?.items || [];

  const findings = useMemo(
    () => dedupeOpenFindings(rawFindings),
    [rawFindings],
  );

  const openTotal = summary?.action_centre_open_findings
    ?? summary?.open_findings
    ?? summary?.open_count
    ?? pageData?.total
    ?? findings.length;
  const truncated = Boolean(pageData?.truncated || (openTotal > findings.length));

  const hasFindingsData = rawFindings.length > 0 || Boolean(summary);
  const findingsQueryError = (isError || summaryError) && !hasFindingsData;
  const findingsQueryErrorDetail = error || summaryErrorDetail;
  const findingsRefreshFailed = (isError || summaryError) && hasFindingsData;

  const indexReady = !!subscription && !isLoading && !isError && !summaryLoading && !summaryError;

  const refetchFindings = () => {
    refetch();
    refetchSummary();
  };

  const byResourceId = useMemo(() => {
    const map = new Map();
    for (const f of findings) {
      const expanded = expandFindingRecommendations(f);
      for (const finding of expanded) {
        const key = normalizeArmId(finding.resource_id);
        if (!key) continue;
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(finding);
      }
    }
    for (const [key, bucket] of map.entries()) {
      map.set(key, sortFindingsByPriority(bucket));
    }
    return map;
  }, [findings]);

  const savingsByResource = useMemo(
    () => buildSavingsByResourceMap(findings, summary?.savings_by_resource_usd),
    [findings, summary?.savings_by_resource_usd],
  );

  return {
    findings,
    byResourceId,
    savingsByResource,
    summary,
    isLoading,
    isError: findingsQueryError,
    refreshFailed: findingsRefreshFailed,
    error: findingsQueryErrorDetail,
    refetch: refetchFindings,
    indexReady,
    truncated,
    findingsTotal: openTotal,
  };
}

import { fetchBatchResourceLookup } from '../api/azure';

const lookupCache = new Map();

function cacheKey(subscriptionId, resourceId, timespan, flags) {
  return `${subscriptionId}|${resourceId}|${timespan}|${flags.metrics}|${flags.analysis}`;
}

/**
 * Batch-fetch drawer payloads (metrics + advanced analysis) with in-memory dedup.
 */
export async function fetchDrawerResourceBundle({
  subscriptionId,
  resourceId,
  timespan,
  includeMetrics = true,
  includeAdvancedAnalysis = true,
  signal,
}) {
  const key = cacheKey(subscriptionId, resourceId, timespan, {
    metrics: includeMetrics,
    analysis: includeAdvancedAnalysis,
  });
  if (lookupCache.has(key)) {
    return lookupCache.get(key);
  }

  const promise = fetchBatchResourceLookup({
    subscription_id: subscriptionId,
    resource_ids: [resourceId],
    timespan,
    include_metrics: includeMetrics,
    include_advanced_analysis: includeAdvancedAnalysis,
  }, { signal }).then((payload) => {
    const rid = String(resourceId || '').toLowerCase();
    return payload?.items?.[rid] || payload?.items?.[resourceId] || null;
  });

  lookupCache.set(key, promise);
  promise.catch(() => lookupCache.delete(key));
  return promise;
}

export function clearDrawerResourceBundleCache() {
  lookupCache.clear();
}

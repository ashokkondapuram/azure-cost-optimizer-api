import { fetchBatchResourceLookup } from '../api/azure';
import { coerceMetricTimespan } from './metricsTimespanUtils';
import { normalizeArmId } from './findingDedupe';

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
  const normalizedTimespan = coerceMetricTimespan(timespan);
  const key = cacheKey(subscriptionId, resourceId, normalizedTimespan, {
    metrics: includeMetrics,
    analysis: includeAdvancedAnalysis,
  });
  if (lookupCache.has(key)) {
    return lookupCache.get(key);
  }

  const promise = fetchBatchResourceLookup({
    subscription_id: subscriptionId,
    resource_ids: [resourceId],
    timespan: normalizedTimespan,
    include_metrics: includeMetrics,
    include_advanced_analysis: includeAdvancedAnalysis,
    profile: 'drawer',
  }, { signal   }).then((payload) => {
    const rid = normalizeArmId(resourceId);
    const raw = String(resourceId || '').toLowerCase();
    return payload?.items?.[rid] || payload?.items?.[raw] || payload?.items?.[resourceId] || null;
  });

  lookupCache.set(key, promise);
  promise.catch(() => lookupCache.delete(key));
  return promise;
}

export function clearDrawerResourceBundleCache() {
  lookupCache.clear();
}

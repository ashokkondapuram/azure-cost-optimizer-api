import api from './client';

export async function fetchQuotaLocations(subscriptionId) {
  const { data } = await api.get(
    `/quota/${encodeURIComponent(subscriptionId)}/locations`,
  );
  return data;
}

export async function fetchSubscriptionQuota(subscriptionId, location) {
  const { data } = await api.get(
    `/quota/${encodeURIComponent(subscriptionId)}/all`,
    { params: { location } },
  );
  return data;
}

export async function fetchAllRegionsQuota(subscriptionId, locations) {
  const results = await Promise.allSettled(
    locations.map((location) => fetchSubscriptionQuota(subscriptionId, location)),
  );
  const byRegion = [];
  const errors = [];
  for (let i = 0; i < results.length; i += 1) {
    const result = results[i];
    const location = locations[i];
    if (result.status === 'fulfilled') {
      byRegion.push({ location, ...result.value });
    } else {
      errors.push({ location, error: result.reason?.message || 'Failed to load' });
    }
  }

  const items = byRegion.flatMap((region) => (
    (region.items || []).map((item) => ({ ...item, location: region.location }))
  ));

  return {
    subscription_id: subscriptionId,
    mode: 'all_regions',
    regions_loaded: byRegion.length,
    regions_failed: errors.length,
    locations: locations,
    totals: {
      all: items.length,
      compute: items.filter((i) => i.source === 'compute').length,
      network: items.filter((i) => i.source === 'network').length,
      storage: items.filter((i) => i.source === 'storage').length,
      ok: items.filter((i) => i.status === 'ok').length,
    },
    near_limit_count: items.filter((i) => i.status === 'warning').length,
    critical_count: items.filter((i) => i.status === 'critical').length,
    near_limit: items.filter((i) => i.status === 'warning' || i.status === 'critical'),
    items: items.sort(
      (a, b) => (b.usage_pct || 0) - (a.usage_pct || 0) || (a.name || '').localeCompare(b.name || ''),
    ),
    by_region: byRegion,
    errors,
  };
}

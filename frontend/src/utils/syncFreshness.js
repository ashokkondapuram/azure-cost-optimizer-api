export const FRESHNESS_LABEL = {
  fresh: 'Up to date',
  recent: 'Synced recently',
  aging: 'Sync aging',
  stale: 'Sync stale',
  never: 'Not synced',
  unknown: 'Unknown',
  completed: 'Up to date',
  expired: 'Expired',
  empty: 'Not cached',
};

export function formatSyncTime(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return null;
  }
}

export function syncTone(freshness) {
  if (freshness === 'fresh' || freshness === 'recent' || freshness === 'completed') return 'ok';
  if (freshness === 'aging') return 'warn';
  if (freshness === 'expired' || freshness === 'stale') return 'danger';
  return 'muted';
}

export function freshnessLabel(freshness) {
  return FRESHNESS_LABEL[freshness] || freshness || 'Unknown';
}

export const SYNC_STREAMS = [
  { key: 'inventory', label: 'Inventory', meta: (s) => (
    s.resource_count != null ? `${s.resource_count.toLocaleString()} resources` : null
  ) },
  { key: 'cost', label: 'Cost sync', meta: (s) => {
    const amount = s.total_billing > 0 ? s.total_billing : s.total_usd;
    const currency = s.billing_currency || 'CAD';
    return amount > 0 ? `MTD ${amount.toLocaleString()} ${currency}` : null;
  } },
  { key: 'analysis', label: 'Analysis', meta: (s) => (
    s.open_findings != null ? `${s.open_findings} open findings` : null
  ) },
  { key: 'subscriptions_catalog', label: 'Subscriptions', meta: () => null },
  { key: 'token', label: 'Azure token cache', meta: (s) => (
    s.cached ? 'PostgreSQL · encrypted' : 'Fetched on demand'
  ) },
];

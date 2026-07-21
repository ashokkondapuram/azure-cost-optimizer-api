import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { fetchDashboardSyncStatus } from '../../api/azure';
import {
  SYNC_STREAMS,
  formatSyncTime,
  freshnessLabel,
  syncTone,
} from '../../utils/syncFreshness';
import { toDisplayText } from '../../utils/formatDisplay';

function SyncPillsGrid({ status }) {
  if (!status) return null;
  return (
    <div className="data-freshness__grid data-freshness__grid--embedded">
      {SYNC_STREAMS.map(({ key, label, meta }) => {
        const stream = status[key] || {};
        const freshness = stream.freshness || stream.last_status || stream.status || 'never';
        const at = stream.last_synced_at || stream.last_job_at || stream.expires_at || stream.updated_at;
        const metaText = meta(stream);
        return (
          <div
            key={key}
            className={`data-freshness__pill data-freshness__pill--${syncTone(freshness)}`}
          >
            <span className="data-freshness__pill-label">{label}</span>
            <span className="data-freshness__pill-value">{freshnessLabel(freshness)}</span>
            {formatSyncTime(at) && (
              <span className="data-freshness__pill-meta">{formatSyncTime(at)}</span>
            )}
            {metaText && <span className="data-freshness__pill-meta">{metaText}</span>}
            {key === 'token' && stream.expires_at && (
              <span className="data-freshness__pill-meta">
                Expires {formatSyncTime(stream.expires_at)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function DataFreshnessPanel({
  subscription,
  subscriptionLabel,
  sync: syncProp,
  variant = 'default',
  onRefresh,
  isRefreshing = false,
}) {
  const fetchEnabled = !!subscription && syncProp === undefined;
  const { data: fetchedStatus, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['dashboard-sync-status', subscription],
    queryFn: () => fetchDashboardSyncStatus({ subscription_id: subscription }),
    enabled: fetchEnabled,
    staleTime: 30_000,
  });

  const status = syncProp !== undefined ? syncProp : fetchedStatus;
  const loading = fetchEnabled && isLoading;
  const error = fetchEnabled && isError;
  const fetching = fetchEnabled ? isFetching : isRefreshing;

  const handleRefresh = () => {
    if (onRefresh) {
      onRefresh();
    } else if (fetchEnabled) {
      refetch();
    }
  };

  if (!subscription) {
    if (variant === 'embedded') return null;
    return (
      <section className="card data-freshness">
        <p className="data-freshness__hint">Select a subscription in the sidebar to view sync status.</p>
      </section>
    );
  }

  if (variant === 'embedded') {
    return (
      <div className="dashboard-hero__sync">
        <div className="dashboard-hero__sync-head">
          <RefreshCw size={14} aria-hidden className={fetching ? 'spin' : ''} />
          <span>Data freshness</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm dashboard-hero__sync-refresh"
            onClick={handleRefresh}
            disabled={fetching}
          >
            Refresh
          </button>
        </div>
        {loading && <p className="data-freshness__hint">Loading sync status…</p>}
        {error && <p className="data-freshness__error">Could not load sync status.</p>}
        <SyncPillsGrid status={status} />
      </div>
    );
  }

  return (
    <section className="card data-freshness">
      <header className="data-freshness__header">
        <div className="data-freshness__title-row">
          <RefreshCw size={18} aria-hidden className={fetching ? 'spin' : ''} />
          <div>
            <h3 className="dashboard-section__title">Data freshness</h3>
            <p className="dashboard-section__sub">
              {subscriptionLabel ? toDisplayText(subscriptionLabel) : null}
            </p>
          </div>
        </div>
        <div className="data-freshness__actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={handleRefresh}
            disabled={fetching}
          >
            Refresh
          </button>
        </div>
      </header>

      {loading && <p className="data-freshness__hint">Loading sync status…</p>}
      {error && <p className="data-freshness__error">Could not load sync status.</p>}

      <SyncPillsGrid status={status} />
    </section>
  );
}

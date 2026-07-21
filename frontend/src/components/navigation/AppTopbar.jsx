import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { fetchDashboardSyncStatus } from '../../api/azure';
import { formatDateTime } from '../../utils/format';
import {
  formatSubscriptionOptionLabel,
  resolveSubscriptionLabel,
} from '../../utils/subscriptionDisplay';
import SyncProgressBar from '../dashboard/SyncProgressBar';

export default function AppTopbar({
  subscription,
  subscriptionOptions,
  subscriptionName,
  billingCurrency,
  loading,
  error,
  isAdmin = false,
  onAddSubscription,
  onSubscriptionChange,
  showSyncProgress = false,
}) {
  const { data: syncStatus } = useQuery({
    queryKey: ['dashboard-sync-status', subscription],
    queryFn: () => fetchDashboardSyncStatus({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 60_000,
  });

  const costSyncAt = syncStatus?.cost?.last_synced_at || syncStatus?.cost?.updated_at;
  const costSyncLabel = costSyncAt ? formatDateTime(costSyncAt) : 'Not synced yet';
  const resolvedName = subscriptionName
    || resolveSubscriptionLabel(subscription, subscriptionOptions)
    || 'Select subscription';

  const subscriptionControl = subscriptionOptions.length > 1 ? (
    <select
      className="topbar-select"
      value={subscription}
      onChange={(e) => onSubscriptionChange(e.target.value)}
      aria-label="Active subscription"
    >
      <option value="">Select subscription</option>
      {subscriptionOptions.map((s) => (
        <option key={s.subscriptionId} value={s.subscriptionId}>
          {formatSubscriptionOptionLabel(s)}
        </option>
      ))}
    </select>
  ) : (
    <strong>{loading ? 'Loading…' : resolvedName}</strong>
  );

  return (
    <header className="topbar" aria-label="Subscription context">
      <div className="topbar__meta-group">
        <span className="topbar-meta topbar-meta--subscription">
          Subscription · {error ? <strong role="alert">{error}</strong> : subscriptionControl}
          {isAdmin && (
            <button
              type="button"
              className="topbar-add-btn"
              onClick={onAddSubscription}
              aria-label="Add subscription"
              title="Add subscription"
            >
              <Plus size={14} aria-hidden />
            </button>
          )}
          {showSyncProgress && subscription && (
            <SyncProgressBar subscriptionId={subscription} enabled={showSyncProgress} />
          )}
        </span>
        {subscription && (
          <span className="topbar-meta">
            Last cost sync · <strong>{costSyncLabel}</strong>
          </span>
        )}
        {subscription && billingCurrency && (
          <span className="topbar-meta">
            Billing currency · <strong>{billingCurrency}</strong>
          </span>
        )}
      </div>
    </header>
  );
}

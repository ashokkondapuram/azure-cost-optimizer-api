import React from 'react';
import { RefreshCw } from 'lucide-react';
import AssetIcon from './AssetIcon';
import { getErrorMessage } from '../api/errors';
import { PAGE_ICONS } from '../config/assetIcons';

export function LoadingState({ message = 'Loading…' }) {
  return (
    <div className="card empty-state" role="status" aria-live="polite">
      <div className="spin" />
      <p>{message}</p>
    </div>
  );
}

export function SubscriptionRequired({ message = 'Select a subscription from the sidebar to continue.' }) {
  return (
    <div className="card empty-state">
      <AssetIcon iconKey={PAGE_ICONS.subscription} size={36} style={{ opacity: 0.5, margin: '0 auto 1rem' }} />
      <p>{message}</p>
    </div>
  );
}

export function EmptyState({ iconKey, message, children }) {
  return (
    <div className="card empty-state">
      {iconKey && (
        <AssetIcon iconKey={iconKey} size={36} style={{ opacity: 0.45, margin: '0 auto 1rem' }} />
      )}
      <p>{message}</p>
      {children}
    </div>
  );
}

export function QueryErrorState({
  error,
  onRetry,
  title = 'Failed to load data',
  retryLabel = 'Retry',
}) {
  return (
    <div className="card empty-state query-error" role="alert">
      <p style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: '0.35rem' }}>{title}</p>
      <p style={{ color: 'var(--text2)', fontSize: '0.86rem', maxWidth: 480 }}>
        {getErrorMessage(error)}
      </p>
      {onRetry && (
        <button type="button" className="btn btn-secondary" style={{ marginTop: '1rem' }} onClick={onRetry}>
          <RefreshCw size={13} /> {retryLabel}
        </button>
      )}
    </div>
  );
}

import React from 'react';
import { RefreshCw } from 'lucide-react';

/**
 * Standard "Sync from Azure" action for resource inventory pages.
 */
export default function SyncButton({
  onClick,
  syncing = false,
  disabled = false,
  label = 'Sync from Azure',
  syncingLabel = 'Syncing…',
  className = 'btn btn-secondary',
}) {
  return (
    <button
      type="button"
      className={className}
      onClick={onClick}
      disabled={disabled || syncing}
      aria-busy={syncing}
    >
      {syncing ? (
        <div className="spin" style={{ width: 14, height: 14, borderWidth: 2 }} />
      ) : (
        <RefreshCw size={13} />
      )}
      {syncing ? syncingLabel : label}
    </button>
  );
}

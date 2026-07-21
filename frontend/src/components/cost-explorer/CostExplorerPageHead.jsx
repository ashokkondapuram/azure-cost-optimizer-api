import React from 'react';
import { formatDateTime } from '../../utils/format';

function ExportIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

export default function CostExplorerPageHead({
  periodLabel,
  costSyncAt,
  onExport,
  exportLoading,
  adminActions,
}) {
  const syncText = costSyncAt
    ? `Last cost sync ${formatDateTime(costSyncAt)}`
    : 'Cost sync not available yet';

  return (
    <header className="page-head page-head--cost-explorer">
      <div>
        <h1>Cost explorer</h1>
        <div className="page-meta">
          <span className="meta-pill">{periodLabel || 'Month to date'}</span>
          <span className={`meta-pill${costSyncAt ? ' meta-pill--ok' : ''}`}>
            {costSyncAt && <span className="meta-pill__dot" />}
            {syncText}
          </span>
        </div>
      </div>
      <div className="actions">
        {adminActions}
        <button
          type="button"
          className="btn btn-ghost btn-icon"
          aria-label="Export cost data"
          onClick={onExport}
          disabled={exportLoading}
        >
          <ExportIcon />
          {exportLoading ? 'Exporting…' : 'Export'}
        </button>
      </div>
    </header>
  );
}

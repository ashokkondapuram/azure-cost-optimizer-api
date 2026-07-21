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

export default function DashboardPageHead({
  periodLabel,
  analysisAt,
  nextRunLabel,
  onExport,
}) {
  const analysisText = analysisAt
    ? `Analysis ${formatDateTime(analysisAt)}`
    : 'Analysis not run yet';

  return (
    <header className="page-head page-head--dashboard">
      <div>
        <h1>Dashboard</h1>
        <div className="page-meta">
          <span className="meta-pill">{periodLabel || 'Month to date'}</span>
          <span className={`meta-pill${analysisAt ? ' meta-pill--ok' : ''}`}>
            {analysisAt && <span className="meta-pill__dot" />}
            {analysisText}
          </span>
          {nextRunLabel && (
            <span className="meta-pill">{nextRunLabel}</span>
          )}
        </div>
      </div>
      <div className="actions">
        <button
          type="button"
          className="btn btn-ghost btn-icon"
          aria-label="Export dashboard"
          onClick={onExport}
        >
          <ExportIcon />
          Export
        </button>
      </div>
    </header>
  );
}

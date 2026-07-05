import React from 'react';

const SIGNAL_CONFIG = [
  { key: 'has_advisor', countKey: 'advisor_count', label: 'Advisor', className: 'action-signal--advisor' },
  { key: 'has_findings', countKey: 'findings_count', label: 'Engine', className: 'action-signal--engine' },
  { key: 'has_metrics', countKey: 'metrics_count', label: 'Metrics', className: 'action-signal--metrics' },
];

export default function ActionEvidenceSignals({ summary, compact = false }) {
  if (!summary) return <span className="text-muted">—</span>;

  const active = SIGNAL_CONFIG.filter((cfg) => summary[cfg.key]);
  if (!active.length) return <span className="text-muted">—</span>;

  return (
    <div className={`action-evidence-signals${compact ? ' action-evidence-signals--compact' : ''}`}>
      {active.map((cfg) => {
        const count = summary[cfg.countKey];
        return (
          <span
            key={cfg.key}
            className={`action-signal-pill ${cfg.className}`}
            title={`${cfg.label}${count ? `: ${count}` : ''}`}
          >
            {cfg.label}
            {!compact && count > 0 ? ` ${count}` : null}
          </span>
        );
      })}
    </div>
  );
}

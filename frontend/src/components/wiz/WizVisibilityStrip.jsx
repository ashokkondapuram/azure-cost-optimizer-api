import React from 'react';
import { formatCurrency } from '../../utils/format';

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const SEV_COLORS = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#22c55e',
  INFO: '#38bdf8',
};

export default function WizSeverityHeatmap({ bySeverity = {}, total = 0 }) {
  const max = Math.max(total, 1);

  return (
    <div>
      <div className="wiz-sev-heat" role="img" aria-label="Issue severity distribution">
        {SEVERITY_ORDER.map((sev) => {
          const count = bySeverity[sev] ?? 0;
          if (count <= 0) return null;
          return (
            <div
              key={sev}
              className={`wiz-sev-heat__seg wiz-sev-heat__seg--${sev}`}
              style={{ flexGrow: count / max }}
              title={`${sev}: ${count}`}
            />
          );
        })}
      </div>
      <div className="wiz-sev-legend">
        {SEVERITY_ORDER.map((sev) => {
          const count = bySeverity[sev] ?? 0;
          if (total > 0 && count === 0) return null;
          return (
            <span key={sev} className="wiz-sev-legend__item">
              <span
                className="wiz-sev-legend__dot"
                style={{ background: SEV_COLORS[sev] }}
              />
              {sev}
              {' '}
              <strong>{count}</strong>
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function WizSavingsBanner({
  label = 'Recoverable savings',
  savings = 0,
  currency = 'CAD',
  issueCount = 0,
  resourceCount = 0,
  filteredSavings,
  filteredCount,
}) {
  const showFiltered = typeof filteredSavings === 'number' && filteredCount != null;

  return (
    <div className="wiz-impact-banner">
      <div className="wiz-impact-banner__main">
        <div>
          <div className="wiz-impact-banner__label">{label}</div>
          <div className="wiz-impact-banner__value">
            {formatCurrency(savings, { currency, decimals: 0 })}
            <span style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--text2)' }}>/mo</span>
          </div>
        </div>
        <div className="wiz-impact-banner__meta">
          {issueCount.toLocaleString()} open issues
          {resourceCount > 0 && ` · ${resourceCount.toLocaleString()} resources with recommendations`}
        </div>
      </div>
      {showFiltered && filteredCount > 0 && (
        <div className="wiz-impact-banner__chips">
          <span className="wiz-pill wiz-pill--ok">
            Filtered:
            {' '}
            {formatCurrency(filteredSavings, { currency, decimals: 0 })}
            /mo ·
            {' '}
            {filteredCount.toLocaleString()}
            {' '}
            resources
          </span>
        </div>
      )}
    </div>
  );
}

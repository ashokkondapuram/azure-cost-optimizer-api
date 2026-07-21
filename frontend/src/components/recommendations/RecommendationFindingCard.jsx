import React from 'react';
import SeverityChip from '../visual/SeverityChip';
import { formatCurrency } from '../../utils/format';
import { toDisplayText } from '../../utils/formatDisplay';
import { findingAffectedLabel } from '../../utils/recommendationGrouping';

export default function RecommendationFindingCard({
  finding,
  currency = 'CAD',
  selected = false,
  selectable = false,
  onSelectChange,
  onViewDetails,
}) {
  const f = finding;
  const savings = f.estimated_savings_usd > 0
    ? formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })
    : null;
  const mod = (f.severity || 'MEDIUM').toLowerCase();

  return (
    <article
      className={`finding-card finding-card--${mod}${selected ? ' finding-card--selected' : ''}`}
    >
      <div className="finding-card__accent" aria-hidden />
      <div className="finding-card__content">
        {selectable && f.status === 'open' && (
          <label className="finding-card__select" onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={selected}
              onChange={(e) => onSelectChange?.(f.id, e.target.checked)}
              aria-label={`Select ${f.rule_name}`}
            />
          </label>
        )}
        <header className="finding-card__header">
          <SeverityChip severity={f.severity} size={11} />
          <h4 className="finding-card__title">{toDisplayText(f.rule_name)}</h4>
        </header>
        <div className="finding-card__body">
          <span className="finding-card__metric">{findingAffectedLabel(f)}</span>
          {savings && (
            <span className="finding-card__savings">{savings}/mo</span>
          )}
        </div>
        <footer className="finding-card__footer">
          <button
            type="button"
            className="btn btn-ghost btn-sm finding-card__details-btn"
            onClick={() => onViewDetails?.(f)}
          >
            View details
          </button>
        </footer>
      </div>
    </article>
  );
}

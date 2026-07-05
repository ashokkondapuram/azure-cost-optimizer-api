import React from 'react';
import { dimensionLabel, formatScore } from '../../utils/scoreboardUtils';

const DIMENSION_ORDER = ['cost', 'safety', 'effort', 'workload', 'business'];

export default function MultiFacetScore({ dimensions, overall, compact = false }) {
  if (!dimensions) return <span className="text-muted">—</span>;

  return (
    <div className={`multi-facet-score${compact ? ' multi-facet-score--compact' : ''}`}>
      {DIMENSION_ORDER.map((key) => {
        const value = dimensions[key];
        const pct = Math.max(0, Math.min(100, Number(value) || 0));
        return (
          <div key={key} className="multi-facet-score__row" title={`${dimensionLabel(key)}: ${formatScore(value)}`}>
            {!compact && <span className="multi-facet-score__label">{dimensionLabel(key)}</span>}
            <span className="multi-facet-score__track" aria-hidden>
              <span className="multi-facet-score__fill" style={{ width: `${pct}%` }} />
            </span>
            <span className="multi-facet-score__value">{formatScore(value)}</span>
          </div>
        );
      })}
      {!compact && overall != null && (
        <div className="multi-facet-score__overall">
          Overall
          <strong>{formatScore(overall)}</strong>
        </div>
      )}
    </div>
  );
}

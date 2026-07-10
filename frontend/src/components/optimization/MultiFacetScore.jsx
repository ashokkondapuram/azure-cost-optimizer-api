import React from 'react';
import { dimensionLabel, dimensionShortLabel, formatScore, scoreTone } from '../../utils/scoreboardUtils';

const DIMENSION_ORDER = ['cost', 'safety', 'effort', 'workload', 'business'];

function DimensionBar({ dimensionKey, value, compact, grid }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const tone = scoreTone(value);
  const label = grid ? dimensionShortLabel(dimensionKey) : dimensionLabel(dimensionKey);

  return (
    <div
      className={`multi-facet-score__row${grid ? ' multi-facet-score__row--grid' : ''}`}
      title={`${dimensionLabel(dimensionKey)}: ${formatScore(value)}`}
    >
      {!compact && !grid && (
        <span className="multi-facet-score__label">{label}</span>
      )}
      {grid && (
        <span className="multi-facet-score__grid-label">{label}</span>
      )}
      <span className={`multi-facet-score__track multi-facet-score__track--${tone}`} aria-hidden>
        <span className="multi-facet-score__fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="multi-facet-score__value">{formatScore(value)}</span>
    </div>
  );
}

export default function MultiFacetScore({
  dimensions,
  overall,
  compact = false,
  variant = compact ? 'compact' : 'default',
}) {
  if (!dimensions) return <span className="text-muted">—</span>;

  const isGrid = variant === 'grid';
  const isCompact = variant === 'compact' || compact;

  return (
    <div
      className={[
        'multi-facet-score',
        isCompact ? 'multi-facet-score--compact' : '',
        isGrid ? 'multi-facet-score--grid' : '',
      ].filter(Boolean).join(' ')}
    >
      {DIMENSION_ORDER.map((key) => (
        <DimensionBar
          key={key}
          dimensionKey={key}
          value={dimensions[key]}
          compact={isCompact}
          grid={isGrid}
        />
      ))}
      {!isCompact && !isGrid && overall != null && (
        <div className="multi-facet-score__overall">
          Overall
          <strong>{formatScore(overall)}</strong>
        </div>
      )}
    </div>
  );
}

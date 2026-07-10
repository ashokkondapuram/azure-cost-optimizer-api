import React, { memo } from 'react';
import { ChevronDown, ExternalLink } from 'lucide-react';
import ActionResourceCell from '../optimization/ActionResourceCell';
import MultiFacetScore from '../optimization/MultiFacetScore';
import OptimizationActionChip from '../optimization/OptimizationActionChip';
import ConfidenceScore from '../optimization/ConfidenceScore';
import { formatCurrency } from '../../utils/format';
import { formatScore, scoreTone, tierLabel, tierTone } from '../../utils/scoreboardUtils';

function ScoreboardTableRow({
  row,
  currency,
  expanded,
  onToggleExpand,
  onOpenDetails,
}) {
  const overallTone = scoreTone(row.overall_recommendation_score);
  const savings = Number(row.cost_savings_monthly) || 0;
  const risk = formatScore(row.performance_risk_score);

  return (
    <>
      <tr
        className={`scoreboard-row${expanded ? ' scoreboard-row--expanded' : ''}`}
        onClick={onToggleExpand}
      >
        <td className="scoreboard-row__resource" data-label="Resource">
          <ActionResourceCell action={row} />
        </td>
        <td className="scoreboard-row__score" data-label="Score">
          <div className="scoreboard-score-stack">
            <span className={`scoreboard-overall scoreboard-overall--${overallTone}`}>
              {formatScore(row.overall_recommendation_score)}
            </span>
            <span className={`tier-pill tier-pill--${tierTone(row.recommendation_tier)}`}>
              {tierLabel(row.recommendation_tier, { short: true })}
            </span>
          </div>
        </td>
        <td className="scoreboard-row__dimensions" data-label="Dimensions">
          <MultiFacetScore
            dimensions={row.dimensions}
            overall={row.overall_recommendation_score}
            variant="grid"
          />
        </td>
        <td className="scoreboard-row__recommendation" data-label="Recommendation">
          <div className="scoreboard-rec-stack">
            <div className="scoreboard-rec-stack__primary">
              <OptimizationActionChip actionType={row.primary_action} compact />
              <ConfidenceScore confidence={row.action_confidence} compact />
            </div>
            <div className="scoreboard-rec-stack__meta">
              <span className={savings > 0 ? 'scoreboard-rec-stack__savings' : 'text-muted'}>
                {savings > 0 ? formatCurrency(savings, { currency }) : 'No savings est.'}
              </span>
              <span className="scoreboard-rec-stack__risk">
                Risk
                {' '}
                <strong>{risk}</strong>
              </span>
            </div>
          </div>
        </td>
        <td className="scoreboard-row__actions" data-label="Details">
          <div className="scoreboard-row__actions-inner">
            <button
              type="button"
              className={`scoreboard-row__expand${expanded ? ' scoreboard-row__expand--open' : ''}`}
              aria-expanded={expanded}
              aria-label={expanded ? 'Collapse score details' : 'Expand score details'}
              onClick={(event) => {
                event.stopPropagation();
                onToggleExpand();
              }}
            >
              <ChevronDown size={16} aria-hidden />
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm scoreboard-row__details"
              onClick={(event) => {
                event.stopPropagation();
                onOpenDetails();
              }}
            >
              <ExternalLink size={14} aria-hidden />
              View
            </button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="scoreboard-row__detail">
          <td colSpan={5}>
            <div className="scoreboard-detail-panel">
              <div className="scoreboard-detail-panel__section">
                <h3 className="scoreboard-detail-panel__title">Dimension breakdown</h3>
                <MultiFacetScore
                  dimensions={row.dimensions}
                  overall={row.overall_recommendation_score}
                />
              </div>
              <div className="scoreboard-detail-panel__section scoreboard-detail-panel__section--meta">
                <dl className="scoreboard-detail-meta">
                  <div>
                    <dt>Tier</dt>
                    <dd>{tierLabel(row.recommendation_tier)}</dd>
                  </div>
                  <div>
                    <dt>Overall score</dt>
                    <dd>{formatScore(row.overall_recommendation_score)}</dd>
                  </div>
                  <div>
                    <dt>Performance risk</dt>
                    <dd>{risk}</dd>
                  </div>
                  <div>
                    <dt>Est. savings</dt>
                    <dd>{savings > 0 ? formatCurrency(savings, { currency }) : '—'}</dd>
                  </div>
                  {row.evaluation_date && (
                    <div>
                      <dt>Evaluated</dt>
                      <dd>{row.evaluation_date}</dd>
                    </div>
                  )}
                </dl>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default memo(ScoreboardTableRow);

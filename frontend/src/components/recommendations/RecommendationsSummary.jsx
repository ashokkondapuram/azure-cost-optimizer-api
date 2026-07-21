import React from 'react';
import { formatCurrency } from '../../utils/format';
import SeverityChip from '../visual/SeverityChip';
import { summarizeBySeverity } from '../../utils/recommendationGrouping';

export default function RecommendationsSummary({
  findings = [],
  currency = 'CAD',
}) {
  const { groups, totalCount, totalSavings } = summarizeBySeverity(findings);
  if (!totalCount) return null;

  const annualSavings = totalSavings * 12;

  return (
    <section className="rec-summary card" aria-label="Open findings summary">
      <header className="rec-summary__head">
        <h3 className="rec-summary__title">Open findings summary</h3>
        <p className="rec-summary__total">
          {totalCount.toLocaleString()} findings
          {totalSavings > 0 && (
            <>
              {' · '}
              {formatCurrency(totalSavings, { currency, decimals: 0 })}/mo potential
              {' · '}
              Est. annual {formatCurrency(annualSavings, { currency, decimals: 0 })}
            </>
          )}
        </p>
      </header>
      <div className="rec-summary__grid">
        {groups.map((group) => (
          <div
            key={group.severity}
            className={`rec-summary__row rec-summary__row--${group.severity.toLowerCase()}`}
          >
            <SeverityChip severity={group.severity} size={11} />
            <span className="rec-summary__count">
              {group.findings.length.toLocaleString()}
            </span>
            {group.savings > 0 && (
              <span className="rec-summary__savings">
                {formatCurrency(group.savings, { currency, decimals: 0 })}/mo
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

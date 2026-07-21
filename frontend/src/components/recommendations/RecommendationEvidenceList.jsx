import React from 'react';
import SeverityChip from '../visual/SeverityChip';
import { formatCurrency } from '../../utils/format';
import RuleEvidenceTable from './RuleEvidenceTable';

/**
 * Numbered list of recommendations with per-rule savings and evidence signals.
 */
export default function RecommendationEvidenceList({
  items = [],
  currency = 'CAD',
  resourceName = '',
  className = '',
}) {
  if (!items.length) return null;

  const title = resourceName
    ? `Finding: ${resourceName}`
    : 'Recommendations';

  return (
    <section className={`rec-evidence-list-panel${className ? ` ${className}` : ''}`}>
      <header className="rec-evidence-list-panel__head">
        <h3 className="rec-evidence-list-panel__title">{title}</h3>
        {items.length > 1 ? (
          <span className="rec-evidence-list-panel__count">
            {items.length}
            {' '}
            recommendations
          </span>
        ) : null}
      </header>
      <ol className="rec-evidence-list-panel__items">
        {items.map((item, index) => (
          <li key={item.id || `${item.ruleId}-${index}`} className="rec-evidence-list-panel__item">
            <div className="rec-evidence-list-panel__item-head">
              <span className="rec-evidence-list-panel__index">{index + 1}</span>
              <div className="rec-evidence-list-panel__item-title-wrap">
                <strong className="rec-evidence-list-panel__item-title">{item.title}</strong>
                {item.severity ? (
                  <SeverityChip severity={item.severity} size={10} />
                ) : null}
              </div>
              {item.savings > 0 ? (
                <span className="rec-evidence-list-panel__savings">
                  Save
                  {' '}
                  {formatCurrency(item.savings, { currency, decimals: 0 })}
                  /mo
                </span>
              ) : null}
            </div>
            {item.recommendation && item.recommendation !== '—' ? (
              <p className="rec-evidence-list-panel__item-rec">{item.recommendation}</p>
            ) : null}
            <RuleEvidenceTable rows={item.evidenceRows} factors={item.factors} compact />
          </li>
        ))}
      </ol>
    </section>
  );
}

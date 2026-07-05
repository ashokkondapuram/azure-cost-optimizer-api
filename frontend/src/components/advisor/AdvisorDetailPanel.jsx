import React from 'react';
import { toDisplayText } from '../../utils/formatDisplay';
import { formatCurrency } from '../../utils/format';
import {
  advisorCategoryLabel,
  advisorImpactTone,
  advisorMonthlySavings,
} from '../../utils/advisorUtils';
import AdvisorRecommendationBadge from './AdvisorRecommendationBadge';

function AdvisorRecommendationCard({ recommendation, currency }) {
  const savings = advisorMonthlySavings(recommendation);
  const tone = advisorImpactTone(recommendation.impact);

  return (
    <article className={`advisor-detail-card advisor-detail-card--${tone}`}>
      <header className="advisor-detail-card__header">
        <AdvisorRecommendationBadge recommendation={recommendation} currency={currency} />
        {recommendation.status && recommendation.status !== 'Active' && (
          <span className="advisor-detail-card__status">{recommendation.status}</span>
        )}
      </header>
      <h4 className="advisor-detail-card__title">{toDisplayText(recommendation.summary)}</h4>
      {recommendation.description && (
        <p className="advisor-detail-card__description">
          {toDisplayText(recommendation.description)}
        </p>
      )}
      <dl className="advisor-detail-card__meta">
        {savings != null && savings > 0 && (
          <>
            <dt>Est. savings</dt>
            <dd>{formatCurrency(savings, { currency, decimals: 0 })}/mo</dd>
          </>
        )}
        <dt>Category</dt>
        <dd>{advisorCategoryLabel(recommendation.category)}</dd>
        <dt>Impact</dt>
        <dd>{recommendation.impact || '—'}</dd>
      </dl>
    </article>
  );
}

export default function AdvisorDetailPanel({
  recommendations = [],
  indexReady = true,
  isLoading = false,
  currency = 'USD',
  emptyMessage = 'No Azure Advisor recommendations for this resource yet.',
}) {
  if (isLoading || !indexReady) {
    return <p className="text-muted" style={{ fontSize: '0.85rem' }}>Loading Advisor recommendations…</p>;
  }
  if (!recommendations.length) {
    return (
      <p className="text-muted advisor-detail-panel__empty" style={{ fontSize: '0.85rem', margin: 0 }}>
        {emptyMessage}
      </p>
    );
  }

  return (
    <div className="advisor-detail-panel">
      {recommendations.map((rec) => (
        <AdvisorRecommendationCard
          key={rec.id || rec.recommendation_id}
          recommendation={rec}
          currency={currency}
        />
      ))}
    </div>
  );
}

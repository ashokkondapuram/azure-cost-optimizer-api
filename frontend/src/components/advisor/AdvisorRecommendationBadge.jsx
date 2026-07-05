import React from 'react';
import { toDisplayText } from '../../utils/formatDisplay';
import {
  advisorCategoryLabel,
  advisorImpactTone,
  advisorMonthlySavings,
  advisorSavingsLabel,
} from '../../utils/advisorUtils';
import AdvisorCategoryIcon from './AdvisorCategoryIcon';

export default function AdvisorRecommendationBadge({
  recommendation,
  compact = false,
  showSavings = true,
  currency = 'USD',
}) {
  if (!recommendation) return null;

  const category = recommendation.category;
  const impact = recommendation.impact;
  const tone = advisorImpactTone(impact);
  const savings = advisorMonthlySavings(recommendation);
  const savingsText = showSavings ? advisorSavingsLabel(savings, currency) : null;

  return (
    <span
      className={`advisor-badge advisor-badge--${tone}${compact ? ' advisor-badge--compact' : ''}`}
      title={toDisplayText(recommendation.summary)}
    >
      <AdvisorCategoryIcon category={category} size={compact ? 11 : 13} />
      <span className="advisor-badge__category">{advisorCategoryLabel(category)}</span>
      {!compact && impact && (
        <span className="advisor-badge__impact">{impact}</span>
      )}
      {savingsText && (
        <span className="advisor-badge__savings">{savingsText}</span>
      )}
    </span>
  );
}

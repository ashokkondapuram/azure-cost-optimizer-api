import React from 'react';
import { Link } from 'react-router-dom';
import AdvisorRecommendationBadge from './AdvisorRecommendationBadge';
import { primaryAdvisorRecommendation } from '../../utils/advisorUtils';

export default function AdvisorTableCell({
  recommendations = [],
  indexReady = true,
  isError = false,
  currency = 'CAD',
  subscriptionHasAdvisor = false,
}) {
  if (!indexReady) {
    return <span className="resource-table__empty" title="Loading Advisor recommendations">…</span>;
  }
  if (isError) {
    return (
      <span className="resource-table__empty resource-table__empty--warn" title="Could not load Advisor recommendations">
        !
      </span>
    );
  }
  const primary = primaryAdvisorRecommendation(recommendations);
  if (!primary) {
    if (subscriptionHasAdvisor) {
      return <span className="resource-table__empty" title="No Advisor recommendations for this resource">—</span>;
    }
    return (
      <Link
        to="/admin/optimization"
        className="advisor-table-cell advisor-table-cell--sync-hint text-sm"
        title="Sync Azure Advisor from Optimization center"
        onClick={(e) => e.stopPropagation()}
      >
        Sync Advisor
      </Link>
    );
  }
  const extra = recommendations.length > 1 ? ` +${recommendations.length - 1}` : '';
  return (
    <span className="advisor-table-cell">
      <AdvisorRecommendationBadge recommendation={primary} compact showSavings currency={currency} />
      {extra && <span className="advisor-table-cell__more">{extra}</span>}
    </span>
  );
}

import React from 'react';
import { Lightbulb } from 'lucide-react';
import AdvisorDetailPanel from './AdvisorDetailPanel';

export default function AdvisorResourceSection({
  recommendations = [],
  indexReady = true,
  isLoading = false,
  currency = 'CAD',
  subscriptionHasAdvisor = false,
  bare = false,
}) {
  const hasRecs = recommendations.length > 0;

  const body = hasRecs ? (
    <AdvisorDetailPanel
      recommendations={recommendations}
      indexReady={indexReady}
      isLoading={isLoading}
      currency={currency}
    />
  ) : (
    <div className="advisor-resource-empty">
      {indexReady && !isLoading && (
        subscriptionHasAdvisor ? (
          <p className="text-muted text-sm">No Azure Advisor recommendations for this resource.</p>
        ) : (
          <>
            <p className="text-muted text-sm">
              Advisor data has not been synced for this subscription. Sync Advisor in Sync center.
            </p>
          </>
        )
      )}
      {isLoading && <p className="text-muted text-sm">Loading Advisor…</p>}
    </div>
  );

  if (bare) {
    return <div className="insight-drawer__bare-content">{body}</div>;
  }

  return (
    <div className="insight-drawer__inline-section insight-drawer__advisor-section">
      <div className="insight-drawer__property-group-title insight-drawer__inline-section-head">
        <span className="insight-drawer__inline-section-title">
          <Lightbulb size={13} aria-hidden />
          Azure Advisor
          {hasRecs ? (
            <span className="insight-drawer__flow-badge">{recommendations.length}</span>
          ) : null}
        </span>
      </div>
      <p className="insight-drawer__inline-section-hint text-muted text-sm">
        Recommendations from Microsoft Azure Advisor for this resource.
      </p>
      {body}
    </div>
  );
}

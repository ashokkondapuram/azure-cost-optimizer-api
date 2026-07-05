import React from 'react';
import { Link } from 'react-router-dom';
import { Lightbulb } from 'lucide-react';
import DrawerCollapsibleSection from '../DrawerCollapsibleSection';
import AdvisorDetailPanel from './AdvisorDetailPanel';

export default function AdvisorResourceSection({
  recommendations = [],
  indexReady = true,
  isLoading = false,
  currency = 'CAD',
  subscriptionHasAdvisor = false,
}) {
  const hasRecs = recommendations.length > 0;

  return (
    <DrawerCollapsibleSection
      title="Azure Advisor"
      icon={<Lightbulb size={13} />}
      variant="info"
      defaultOpen={hasRecs || subscriptionHasAdvisor}
      compact
      badge={hasRecs ? recommendations.length : null}
      hint="Recommendations from Microsoft Azure Advisor for this resource."
    >
      {hasRecs ? (
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
                  Advisor data has not been synced for this subscription.
                </p>
                <Link to="/admin/optimization" className="btn btn-ghost btn-sm">
                  Sync Advisor in Optimization center
                </Link>
              </>
            )
          )}
          {isLoading && <p className="text-muted text-sm">Loading Advisor…</p>}
        </div>
      )}
    </DrawerCollapsibleSection>
  );
}

import React from 'react';
import RecommendationDetailCard from '../RecommendationDetailCard';
import OptimizationGroupPanel from './OptimizationGroupPanel';

export default function FindingsGroupedView({
  groups,
  currency,
  subscriptionId,
  onStatusChange,
  statusPending,
  allowResolve,
  showStatus,
  selectableFindings,
  selectedIds,
  onSelectChange,
}) {
  return (
    <div className="opt-grouped-findings">
      {groups.map((group) => (
        <OptimizationGroupPanel
          key={group.key}
          groupKey={group.key}
          title={group.label}
          count={`${group.items.length} recommendation${group.items.length === 1 ? '' : 's'}`}
          savings={group.savings}
          currency={currency}
        >
          <div className="opt-grouped-findings__list">
            {group.items.map((finding) => (
              <RecommendationDetailCard
                key={finding.id}
                finding={finding}
                currency={currency}
                subscriptionId={subscriptionId}
                onStatusChange={onStatusChange}
                statusPending={statusPending}
                allowResolve={allowResolve}
                showStatus={showStatus}
                compact
                defaultExpanded={false}
                selectable={finding.status === 'open'}
                selected={selectedIds?.has(finding.id)}
                onSelectChange={onSelectChange}
              />
            ))}
          </div>
        </OptimizationGroupPanel>
      ))}
    </div>
  );
}

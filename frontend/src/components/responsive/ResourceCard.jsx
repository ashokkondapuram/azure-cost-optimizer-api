import React from 'react';
import AssetIcon from '../AssetIcon';
import FindingsBadge from '../FindingsBadge';
import AdvisorTableCell from '../advisor/AdvisorTableCell';
import { formatCurrency } from '../../utils/format';
import { resourceTotalCost } from '../../utils/costCurrency';
import { iconForRow } from '../../config/assetIcons';

function StateBadge({ stateText, status }) {
  const lower = String(stateText || '').toLowerCase();
  const isMissing = status === 'missing' || /doesn't exist on azure/i.test(stateText);
  const isUnknown = status === 'unknown' || stateText === '—';
  return (
    <span className={`badge resource-state-badge resource-card__state ${
      isMissing ? 'badge-critical'
        : isUnknown ? 'badge-medium'
        : /running|active|enabled|succeeded|attached/i.test(stateText) ? 'badge-low'
        : /stopped|deallocated|disabled|unattached|unassociated/i.test(stateText) ? 'badge-critical'
        : 'badge-medium'
    }`}
    >
      {stateText}
    </span>
  );
}

export default function ResourceCard({
  row,
  nameLabel,
  stateText,
  showState,
  showCost,
  currency,
  apiPath,
  pageIcon,
  indexFindings = [],
  savings = 0,
  indexReady,
  advisorRecommendations = [],
  advisorIndexReady,
  advisorIndexError,
  subscriptionHasAdvisor,
  subscriptionHasFindings,
  onSelect,
}) {
  return (
    <button
      type="button"
      className="resource-card"
      onClick={() => onSelect(row)}
    >
      <div className="resource-card__head">
        <AssetIcon iconKey={iconForRow(row, { apiPath, fallback: pageIcon })} size={20} />
        <div className="resource-card__title">
          <span className="resource-card__name">{nameLabel}</span>
          {showState && stateText && (
            <StateBadge stateText={stateText} status={row.azureStatus} />
          )}
        </div>
      </div>
      <div className="resource-card__meta">
        {showCost && (
          <span className="resource-card__cost">
            {resourceTotalCost(row) > 0
              ? formatCurrency(resourceTotalCost(row), { currency })
              : '—'}
          </span>
        )}
        <FindingsBadge
          resource={row}
          indexFindings={indexFindings}
          savings={savings}
          currency={currency}
          indexReady={indexReady}
        />
        <AdvisorTableCell
          recommendations={advisorRecommendations}
          findings={indexFindings}
          indexReady={advisorIndexReady}
          findingsIndexReady={indexReady}
          isError={advisorIndexError}
          subscriptionHasAdvisor={subscriptionHasAdvisor}
          subscriptionHasFindings={subscriptionHasFindings}
        />
      </div>
    </button>
  );
}

export function ResourceCardGroup({ resourceGroup, rows, children }) {
  return (
    <section className="resource-card-group">
      <header className="resource-card-group__header">
        <span>{resourceGroup}</span>
        <span className="resource-card-group__count">{rows.length}</span>
      </header>
      {children}
    </section>
  );
}

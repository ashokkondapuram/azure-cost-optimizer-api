import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import SeverityChip from './visual/SeverityChip';
import { StatusBadge } from './FindingBadges';
import RecommendationDetailCard from './RecommendationDetailCard';
import RecommendationHelpTooltip from './RecommendationHelpTooltip';
import { formatCurrency } from '../utils/format';
import { sortFindingsByPriority } from '../utils/taxonomy';
import { sumUnifiedSavingsForFindings } from '../utils/unifiedSavings';
import { pickPrimaryCosmosFinding } from '../utils/cosmosPrimaryFinding';
import { buildRationale } from '../utils/insightCanvasUtils';
import { toDisplayText } from '../utils/formatDisplay';

function DrawerFindingRow({
  finding,
  currency,
  expanded,
  onToggle,
  isPrimary,
  resourceTypeLabel,
  inventoryContext,
  resourceRow,
  monthlyResourceCost,
  subscriptionId,
  onStatusChange,
  statusPending,
}) {
  const savingsUsd = Number(finding.estimated_savings_usd) > 0;
  const rationale = buildRationale(finding);
  const detailId = `drawer-finding-${finding.id}`;

  return (
    <li className={`drawer-findings-list__item${expanded ? ' drawer-findings-list__item--expanded' : ''}`}>
      <button
        type="button"
        className="drawer-findings-list__row"
        onClick={() => onToggle(finding.id)}
        aria-expanded={expanded}
        aria-controls={detailId}
      >
        <SeverityChip severity={finding.severity} size={11} />
        <span className="drawer-findings-list__title">
          <RecommendationHelpTooltip
            finding={finding}
            compact
            detailHint={expanded ? 'Details below' : 'Select to view details'}
          >
            {finding.rule_name}
          </RecommendationHelpTooltip>
        </span>
        {isPrimary && (
          <span className="drawer-findings-list__primary">Primary</span>
        )}
        {savingsUsd && (
          <span className={`drawer-findings-list__savings${finding.estimated_savings_usd > 500 ? ' drawer-findings-list__savings--high' : ''}`}>
            {formatCurrency(finding.estimated_savings_usd, { currency, decimals: 0 })}/mo
          </span>
        )}
        {finding.status && finding.status !== 'open' && (
          <StatusBadge status={finding.status} size={10} />
        )}
        <ChevronDown
          size={14}
          className={`drawer-findings-list__chevron${expanded ? ' drawer-findings-list__chevron--open' : ''}`}
          aria-hidden
        />
      </button>
      {!expanded && rationale && (
        <p className="drawer-findings-list__preview">{toDisplayText(rationale)}</p>
      )}
      {expanded && (
        <div id={detailId} className="drawer-findings-list__detail" role="region">
          <RecommendationDetailCard
            finding={finding}
            currency={currency}
            subscriptionId={subscriptionId}
            onStatusChange={onStatusChange}
            statusPending={statusPending}
            hideSeverity
            compact
            bodyOnly
            drawerEvidence
            resourceTypeLabel={resourceTypeLabel}
            inventoryContext={inventoryContext}
            resourceRow={resourceRow}
            monthlyResourceCost={monthlyResourceCost}
          />
        </div>
      )}
    </li>
  );
}

/**
 * Compact vertical list of all open findings for the resource insight drawer.
 */
export default function DrawerFindingsList({
  findings = [],
  emptyMessage,
  currency = 'CAD',
  resourceTypeLabel = '',
  resourceId = '',
  inventoryContext = null,
  resourceRow = null,
  monthlyResourceCost = 0,
  subscriptionId,
  onStatusChange,
  statusPending = false,
  markPrimary = false,
}) {
  const sorted = useMemo(() => sortFindingsByPriority(findings), [findings]);
  const primaryId = useMemo(() => {
    if (!markPrimary || sorted.length <= 1) return null;
    return pickPrimaryCosmosFinding(sorted)?.id || sorted[0]?.id || null;
  }, [markPrimary, sorted]);

  const [expandedId, setExpandedId] = useState(() => primaryId || sorted[0]?.id || null);

  useEffect(() => {
    setExpandedId(primaryId || sorted[0]?.id || null);
  }, [resourceId, primaryId, sorted]);

  const handleToggle = (findingId) => {
    setExpandedId((prev) => (prev === findingId ? null : findingId));
  };

  if (!sorted.length) {
    return <p className="insight-drawer__empty">{emptyMessage}</p>;
  }

  const totalSavings = sumUnifiedSavingsForFindings(sorted);

  return (
    <div className="drawer-findings-list">
      <div className="drawer-findings-list__summary">
        <span className="drawer-findings-list__count">
          {sorted.length} recommendation{sorted.length === 1 ? '' : 's'}
        </span>
        {totalSavings > 0 && (
          <span className="drawer-findings-list__savings-total">
            {formatCurrency(totalSavings, { currency, decimals: 0 })}/mo potential savings
          </span>
        )}
      </div>
      <ul className="drawer-findings-list__items">
        {sorted.map((finding) => (
          <DrawerFindingRow
            key={finding.id}
            finding={finding}
            currency={currency}
            expanded={expandedId === finding.id}
            onToggle={handleToggle}
            isPrimary={markPrimary && finding.id === primaryId}
            resourceTypeLabel={resourceTypeLabel}
            inventoryContext={inventoryContext}
            resourceRow={resourceRow}
            monthlyResourceCost={monthlyResourceCost}
            subscriptionId={subscriptionId}
            onStatusChange={onStatusChange}
            statusPending={statusPending}
          />
        ))}
      </ul>
    </div>
  );
}

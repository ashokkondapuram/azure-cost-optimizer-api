import React, { useEffect, useMemo, useState } from 'react';
import { SeverityIcon, SEVERITY_META } from './FinOpsIcons';
import { formatCurrency } from '../utils/format';
import { sumUnifiedSavingsForFindings } from '../utils/unifiedSavings';
import { groupFindingsBySeverity } from '../utils/recommendationGrouping';
import { groupFindingsByPillar } from '../utils/pillarEvidence';
import RecommendationDetailCard from './RecommendationDetailCard';
import RecommendationTileCard from './RecommendationTileCard';

function SeverityFilterChip({ group, active, onToggle, compact }) {
  const meta = SEVERITY_META[group.severity] || SEVERITY_META.INFO;

  if (compact) {
    return (
      <button
        type="button"
        className={`insight-severity-chip${active ? ' insight-severity-chip--active' : ''}`}
        style={{
          '--severity-color': meta.color,
        }}
        onClick={onToggle}
        aria-pressed={active}
      >
        <SeverityIcon severity={group.severity} size={12} />
        <span>{group.label}</span>
        <span className="insight-severity-chip__count">{group.findings.length}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      className={`insight-severity-ring insight-severity-ring--${group.severity.toLowerCase()}${active ? ' insight-severity-ring--active' : ''}`}
      onClick={onToggle}
      aria-pressed={active}
      aria-label={`${group.label}, ${group.findings.length} recommendation${group.findings.length === 1 ? '' : 's'}`}
    >
      <span
        className="insight-severity-ring__circle"
        style={{
          borderColor: meta.color,
          color: active ? '#fff' : meta.color,
          background: active ? meta.color : `color-mix(in srgb, ${meta.color} 14%, transparent)`,
        }}
      >
        {group.findings.length}
      </span>
      <span className="insight-severity-ring__label">{group.label}</span>
    </button>
  );
}

export default function InsightFindingsPanel({
  findings = [],
  emptyMessage,
  currency = 'CAD',
  resourceTypeLabel = '',
  resourceId = '',
  inventoryContext = null,
  monthlyResourceCost = 0,
  compact = false,
  showAllByDefault = false,
  primaryOnly = false,
  tileLayout = false,
  subscriptionId,
  onStatusChange,
  statusPending = false,
}) {
  const groups = useMemo(
    () => (compact && !primaryOnly
      ? groupFindingsByPillar(findings)
      : groupFindingsBySeverity(findings)),
    [findings, compact, primaryOnly],
  );
  const isPillarGrouping = compact && !primaryOnly;
  const allFilterKeys = useMemo(
    () => groups.map((g) => (isPillarGrouping ? g.pillar : g.severity)),
    [groups, isPillarGrouping],
  );
  const filterKey = useMemo(
    () => groups.map((g) => (isPillarGrouping ? g.pillar : g.severity)).join(','),
    [groups, isPillarGrouping],
  );

  const [activeFilters, setActiveFilters] = useState(() => new Set());
  const [expandedTileId, setExpandedTileId] = useState(null);

  useEffect(() => {
    if (tileLayout && primaryOnly && findings[0]?.id) {
      setExpandedTileId(findings[0].id);
      return;
    }
    if (tileLayout) {
      setExpandedTileId(null);
    }
  }, [resourceId, tileLayout, primaryOnly, findings]);

  const handleTileToggle = (findingId) => {
    setExpandedTileId((prev) => (prev === findingId ? null : findingId));
  };

  useEffect(() => {
    if ((showAllByDefault || primaryOnly) && filterKey) {
      setActiveFilters(new Set(filterKey.split(',')));
    } else {
      setActiveFilters(new Set());
    }
  }, [resourceId, showAllByDefault, primaryOnly, filterKey]);

  const toggleFilter = (key) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectAll = () => setActiveFilters(new Set(allFilterKeys));
  const clearAll = () => setActiveFilters(new Set());

  if (!findings.length) {
    return <p className="insight-drawer__empty">{emptyMessage}</p>;
  }

  const activeGroups = (showAllByDefault || primaryOnly)
    ? groups
    : groups.filter((g) => activeFilters.has(isPillarGrouping ? g.pillar : g.severity));
  const totalSavings = sumUnifiedSavingsForFindings(findings);

  return (
    <div className={`insight-findings-panel zafin-prose${compact ? ' insight-findings-panel--compact' : ''}`}>
      <div className="insight-findings-panel__summary">
        <span className="insight-findings-panel__count">
          {primaryOnly
            ? 'Best recommendation'
            : `${findings.length} recommendation${findings.length === 1 ? '' : 's'}`}
        </span>
        {totalSavings > 0 && (
          <span className="insight-findings-panel__savings">
            {formatCurrency(totalSavings, { currency, decimals: 0 })}/mo potential savings
          </span>
        )}
      </div>

      {!primaryOnly && !isPillarGrouping && (
        <div className="insight-findings-panel__filters">
          <span className="insight-findings-panel__filters-label">Severity</span>
          <div className="insight-severity-rings" role="group" aria-label="Filter by severity">
            {groups.map((group) => (
              <SeverityFilterChip
                key={group.severity}
                group={group}
                active={activeFilters.has(group.severity)}
                onToggle={() => toggleFilter(group.severity)}
                compact={compact}
              />
            ))}
          </div>
          <div className="insight-findings-panel__filter-actions">
            <button type="button" className="btn btn-ghost btn-sm" onClick={selectAll}>Show all</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={clearAll}>Clear</button>
          </div>
        </div>
      )}

      {activeFilters.size === 0 && !primaryOnly && !showAllByDefault ? (
        <p className="insight-findings-panel__hint">
          {isPillarGrouping
            ? 'No findings to display.'
            : 'Select a severity or choose Show all to view findings.'}
        </p>
      ) : (
        <div className="insight-severity-details">
          {activeGroups.map((group) => {
            const groupKey = isPillarGrouping ? group.pillar : group.severity;
            const groupLabel = isPillarGrouping ? group.label : group.label;
            const groupFindings = group.findings;
            const groupSavings = isPillarGrouping
              ? sumUnifiedSavingsForFindings(groupFindings)
              : group.savings;

            return (
              <div
                key={groupKey}
                className={`insight-severity-details__group insight-severity-details__group--${String(groupKey).toLowerCase()}${isPillarGrouping ? ' insight-severity-details__group--pillar' : ''}`}
              >
                <div className="insight-severity-details__header">
                  {!isPillarGrouping && <SeverityIcon severity={group.severity} size={13} />}
                  <span>{groupLabel}</span>
                  <span className="insight-severity-details__count">{groupFindings.length}</span>
                  {groupSavings > 0 && (
                    <span className="insight-severity-details__savings">
                      {formatCurrency(groupSavings, { currency, decimals: 0 })}/mo
                    </span>
                  )}
                </div>
                <div className={`insight-severity-details__list${tileLayout ? ' insight-severity-details__list--tiles' : ''}`}>
                  {groupFindings.map((finding) => (
                    tileLayout ? (
                      <RecommendationTileCard
                        key={finding.id}
                        finding={finding}
                        currency={currency}
                        expanded={expandedTileId === finding.id}
                        onToggle={handleTileToggle}
                        hideSeverity={isPillarGrouping}
                        resourceTypeLabel={resourceTypeLabel}
                        inventoryContext={inventoryContext}
                        monthlyResourceCost={monthlyResourceCost}
                        subscriptionId={subscriptionId}
                        onStatusChange={onStatusChange}
                        statusPending={statusPending}
                      />
                    ) : (
                      <RecommendationDetailCard
                        key={finding.id}
                        finding={finding}
                        currency={currency}
                        defaultExpanded={showAllByDefault || primaryOnly || (compact && groupFindings.length === 1)}
                        inline={showAllByDefault && compact}
                        hideSeverity={isPillarGrouping}
                        compact
                        resourceTypeLabel={resourceTypeLabel}
                        inventoryContext={inventoryContext}
                        monthlyResourceCost={monthlyResourceCost}
                        subscriptionId={subscriptionId}
                        onStatusChange={onStatusChange}
                        statusPending={statusPending}
                      />
                    )
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

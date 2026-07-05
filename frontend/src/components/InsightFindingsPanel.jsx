import React, { useEffect, useMemo, useState } from 'react';
import { SeverityIcon, SEVERITY_META } from './FinOpsIcons';
import { formatCurrency } from '../utils/format';
import RecommendationDetailCard from './RecommendationDetailCard';

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

const SEVERITY_LABELS = {
  CRITICAL: 'Critical',
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  INFO: 'Info',
};

function groupBySeverity(findings) {
  const buckets = {};
  for (const finding of findings) {
    const severity = finding.severity || 'INFO';
    if (!buckets[severity]) buckets[severity] = [];
    buckets[severity].push(finding);
  }
  return SEVERITY_ORDER
    .filter((severity) => buckets[severity]?.length)
    .map((severity) => ({
      severity,
      label: SEVERITY_LABELS[severity] || severity,
      findings: buckets[severity],
      savings: buckets[severity].reduce((sum, f) => sum + (f.estimated_savings_usd || 0), 0),
    }));
}

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
  compact = false,
  showAllByDefault = false,
}) {
  const groups = useMemo(() => groupBySeverity(findings), [findings]);
  const allSeverities = useMemo(() => new Set(groups.map((g) => g.severity)), [groups]);
  const severityKey = useMemo(() => groups.map((g) => g.severity).join(','), [groups]);

  const [activeSeverities, setActiveSeverities] = useState(() => new Set());

  useEffect(() => {
    if (showAllByDefault && severityKey) {
      setActiveSeverities(new Set(severityKey.split(',')));
    } else {
      setActiveSeverities(new Set());
    }
  }, [resourceId, showAllByDefault, severityKey]);

  const toggleSeverity = (severity) => {
    setActiveSeverities((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  };

  const selectAll = () => setActiveSeverities(new Set(allSeverities));
  const clearAll = () => setActiveSeverities(new Set());

  if (!findings.length) {
    return <p className="insight-drawer__empty">{emptyMessage}</p>;
  }

  const activeGroups = groups.filter((g) => activeSeverities.has(g.severity));
  const totalSavings = findings.reduce((sum, f) => sum + (f.estimated_savings_usd || 0), 0);

  return (
    <div className={`insight-findings-panel${compact ? ' insight-findings-panel--compact' : ''}`}>
      <div className="insight-findings-panel__summary">
        <span className="insight-findings-panel__count">
          {findings.length} recommendation{findings.length === 1 ? '' : 's'}
        </span>
        {totalSavings > 0 && (
          <span className="insight-findings-panel__savings">
            {formatCurrency(totalSavings, { currency, decimals: 0 })}/mo potential savings
          </span>
        )}
      </div>

      <div className="insight-findings-panel__filters">
        <span className="insight-findings-panel__filters-label">Severity</span>
        <div className="insight-severity-rings" role="group" aria-label="Filter by severity">
          {groups.map((group) => (
            <SeverityFilterChip
              key={group.severity}
              group={group}
              active={activeSeverities.has(group.severity)}
              onToggle={() => toggleSeverity(group.severity)}
              compact={compact}
            />
          ))}
        </div>
        <div className="insight-findings-panel__filter-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={selectAll}>Show all</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={clearAll}>Clear</button>
        </div>
      </div>

      {activeSeverities.size === 0 ? (
        <p className="insight-findings-panel__hint">
          Select a severity or choose Show all to view recommendations.
        </p>
      ) : (
        <div className="insight-severity-details">
          {activeGroups.map((group) => (
            <div
              key={group.severity}
              className={`insight-severity-details__group insight-severity-details__group--${group.severity.toLowerCase()}`}
            >
              <div className="insight-severity-details__header">
                <SeverityIcon severity={group.severity} size={13} />
                <span>{group.label}</span>
                <span className="insight-severity-details__count">{group.findings.length}</span>
                {group.savings > 0 && (
                  <span className="insight-severity-details__savings">
                    {formatCurrency(group.savings, { currency, decimals: 0 })}/mo
                  </span>
                )}
              </div>
              <div className="insight-severity-details__list">
                {group.findings.map((finding) => (
                  <RecommendationDetailCard
                    key={finding.id}
                    finding={finding}
                    currency={currency}
                    defaultExpanded={compact && group.findings.length === 1}
                    hideSeverity
                    compact
                    resourceTypeLabel={resourceTypeLabel}
                    inventoryContext={inventoryContext}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

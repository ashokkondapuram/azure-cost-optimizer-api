import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import { formatCurrency } from '../../utils/format';
import SeverityChip from '../visual/SeverityChip';
import RecommendationDetailCard from '../RecommendationDetailCard';
import RecommendationFindingCard from './RecommendationFindingCard';
import {
  SEVERITY_ORDER,
  SEVERITY_LABELS,
  formatCategoryLabel,
  groupFindingsBySeverity,
} from '../../utils/recommendationGrouping';

function defaultExpanded(severity) {
  return severity === 'CRITICAL';
}

export default function RecommendationsSeverityView({
  findings = [],
  currency = 'CAD',
  subscriptionId,
  onStatusChange,
  statusPending = false,
  allowResolve = true,
  showStatus = true,
  selectableFindings = [],
  selectedIds,
  onSelectChange,
  allVisibleSelected = false,
  onSelectAll,
}) {
  const groups = useMemo(() => groupFindingsBySeverity(findings), [findings]);
  const severityKeys = useMemo(() => groups.map((g) => g.severity), [groups]);
  const severityKey = severityKeys.join(',');

  const [visibleSeverities, setVisibleSeverities] = useState(() => new Set(SEVERITY_ORDER));
  const [expandedSeverities, setExpandedSeverities] = useState(() => new Set(['CRITICAL']));
  const [selectedFinding, setSelectedFinding] = useState(null);
  const detailPanelRef = useRef(null);

  useEffect(() => {
    setExpandedSeverities((prev) => {
      const next = new Set(prev);
      for (const sev of severityKeys) {
        if (defaultExpanded(sev)) next.add(sev);
      }
      return next;
    });
    setVisibleSeverities(new Set(SEVERITY_ORDER));
  }, [severityKey, severityKeys]);

  useEffect(() => {
    if (selectedFinding && !findings.some((f) => f.id === selectedFinding.id)) {
      setSelectedFinding(null);
    }
  }, [findings, selectedFinding]);

  useEffect(() => {
    if (selectedFinding && detailPanelRef.current) {
      detailPanelRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [selectedFinding]);

  const toggleVisible = (severity) => {
    setVisibleSeverities((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  };

  const toggleExpanded = (severity) => {
    setExpandedSeverities((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  };

  const expandAll = () => setExpandedSeverities(new Set(severityKeys));
  const collapseAll = () => setExpandedSeverities(new Set());

  const visibleGroups = groups.filter((g) => visibleSeverities.has(g.severity));

  return (
    <div className={`recommendations-split${selectedFinding ? ' recommendations-split--open' : ''}`}>
      <div className="recommendations-split__main">
        <div className="rec-severity-toolbar">
          <div className="rec-severity-toolbar__chips" role="group" aria-label="Show severity groups">
            <button
              type="button"
              className={`btn btn-ghost btn-xs${visibleSeverities.size === SEVERITY_ORDER.length ? ' active' : ''}`}
              onClick={() => setVisibleSeverities(new Set(SEVERITY_ORDER))}
            >
              Show all
            </button>
            {groups.map((group) => {
              const visible = visibleSeverities.has(group.severity);
              const label = SEVERITY_LABELS[group.severity] || group.severity;
              return (
                <button
                  key={group.severity}
                  type="button"
                  className={`rec-severity-toolbar__chip${visible ? ' rec-severity-toolbar__chip--active' : ''}`}
                  onClick={() => toggleVisible(group.severity)}
                  aria-pressed={visible}
                  title={visible ? `Hide ${label} findings` : `Show ${label} findings`}
                >
                  <SeverityChip severity={group.severity} size={10} />
                  <span>{group.findings.length}</span>
                </button>
              );
            })}
          </div>
          <div className="rec-severity-toolbar__actions">
            {selectableFindings.length > 0 && onSelectAll && (
              <label className="rec-severity-toolbar__select-all">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={(e) => onSelectAll(e.target.checked)}
                />
                <span>Select all open</span>
              </label>
            )}
            <button type="button" className="btn btn-ghost btn-xs" onClick={expandAll}>
              <ChevronDown size={12} aria-hidden />
              Expand all
            </button>
            <button type="button" className="btn btn-ghost btn-xs" onClick={collapseAll}>
              <ChevronUp size={12} aria-hidden />
              Collapse all
            </button>
          </div>
        </div>

        {visibleGroups.length === 0 && (
          <p className="rec-severity-hint">Turn on a severity above to view recommendations.</p>
        )}

        <div className="rec-severity-sections">
          {visibleGroups.map((group) => {
            const expanded = expandedSeverities.has(group.severity);
            let lastCategory = null;
            return (
              <section
                key={group.severity}
                className={`rec-severity-section rec-severity-section--${group.severity.toLowerCase()}`}
              >
                <button
                  type="button"
                  className="rec-severity-section__head"
                  onClick={() => toggleExpanded(group.severity)}
                  aria-expanded={expanded}
                >
                  <SeverityChip severity={group.severity} size={12} />
                  <span className="rec-severity-section__title">
                    {group.label}
                    {' '}
                    (
                    {group.findings.length}
                    )
                  </span>
                  {group.savings > 0 && (
                    <span className="rec-severity-section__savings">
                      {formatCurrency(group.savings, { currency, decimals: 0 })}/mo
                    </span>
                  )}
                  <ChevronDown
                    size={16}
                    className={`rec-severity-section__chevron${expanded ? ' rec-severity-section__chevron--open' : ''}`}
                    aria-hidden
                  />
                </button>
                {expanded && (
                  <div className="rec-severity-section__body">
                    {group.findings.map((finding) => {
                      const category = formatCategoryLabel(finding.category);
                      const showCategory = category !== lastCategory;
                      if (showCategory) lastCategory = category;
                      return (
                        <React.Fragment key={finding.id}>
                          {showCategory && (
                            <p className="rec-severity-section__category">{category}</p>
                          )}
                          <RecommendationFindingCard
                            finding={finding}
                            currency={currency}
                            selected={selectedIds?.has(finding.id)}
                            selectable={selectableFindings.some((f) => f.id === finding.id)}
                            onSelectChange={onSelectChange}
                            onViewDetails={setSelectedFinding}
                          />
                        </React.Fragment>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </div>

      {selectedFinding && (
        <aside
          ref={detailPanelRef}
          className="recommendations-detail-panel card"
          aria-label="Recommendation details"
        >
          <header className="recommendations-detail-panel__head">
            <h3 className="recommendations-detail-panel__title">Details</h3>
            <button
              type="button"
              className="btn btn-ghost btn-icon-only"
              aria-label="Close details"
              onClick={() => setSelectedFinding(null)}
            >
              <X size={16} />
            </button>
          </header>
          <div className="recommendations-detail-panel__body">
            <RecommendationDetailCard
              finding={selectedFinding}
              currency={currency}
              subscriptionId={subscriptionId}
              onStatusChange={onStatusChange}
              statusPending={statusPending}
              allowResolve={allowResolve}
              defaultExpanded
              showStatus={showStatus}
            />
          </div>
        </aside>
      )}
    </div>
  );
}

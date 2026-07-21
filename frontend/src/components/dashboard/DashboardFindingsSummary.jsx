import React, { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  findingsLeadText,
  inventoryAffectedPct,
  sourceChipCounts,
} from '../../utils/dashboardV2Utils';

export default function DashboardFindingsSummary({
  summary,
  metrics,
}) {
  const navigate = useNavigate();
  const [activeSource, setActiveSource] = useState('all');

  const chips = useMemo(() => sourceChipCounts(summary), [summary]);
  const lead = useMemo(
    () => findingsLeadText(summary, activeSource, metrics.resourcesAffected),
    [summary, activeSource, metrics.resourcesAffected],
  );

  const inventoryPct = inventoryAffectedPct(
    metrics.resourcesAffected,
    metrics.inventoryTotal,
  );

  const gapsExcluded = metrics.excludedGaps;

  const goActionCentre = () => navigate('/action-centre');

  return (
    <section className="findings-summary" aria-label="Findings summary">
      <div className="findings-summary__hero">
        <div className="findings-summary__copy">
          <h2 className="section-title section-title--bar">Findings summary</h2>
          <p className="findings-summary__lead">{lead}</p>
          <div className="source-chips" role="group" aria-label="Open issues by source">
            {chips.map((chip) => {
              const label = chip.id === 'all'
                ? chip.label
                : `${chip.label} · ${chip.count}`;
              return (
                <button
                  key={chip.id}
                  type="button"
                  className={`source-chip${activeSource === chip.id ? ' active' : ''}`}
                  onClick={() => setActiveSource(chip.id)}
                >
                  {chip.color && (
                    <span className="source-chip__dot" style={{ '--c': chip.color }} />
                  )}
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="findings-summary__stats">
          <div className="stat-block">
            <span className="stat-block__value">{metrics.resourcesAffected.toLocaleString()}</span>
            <span className="stat-block__label">Resources affected</span>
            <div className="stat-block__meter">
              {inventoryPct != null && (
                <span style={{ width: `${Math.min(inventoryPct, 100)}%` }} />
              )}
            </div>
            <span className="stat-block__hint">
              {inventoryPct != null
                ? `${inventoryPct}% of inventory`
                : 'Inventory total unavailable'}
            </span>
          </div>
          <div className="stat-block">
            <span className="stat-block__value stat-block__value--muted">
              {metrics.withSavings.toLocaleString()}
            </span>
            <span className="stat-block__label">With savings data</span>
            <span className="stat-block__hint">
              {gapsExcluded} gap{gapsExcluded === 1 ? '' : 's'} excluded
            </span>
          </div>
        </div>
      </div>
      <div className="findings-summary__workflow" aria-label="Action workflow">
        <button type="button" className="workflow-pill" onClick={goActionCentre}>
          <span className="workflow-pill__num">{metrics.proposed.toLocaleString()}</span>
          <span className="workflow-pill__label">Proposed</span>
        </button>
        <span className="workflow-pill__arrow" aria-hidden="true" />
        <button
          type="button"
          className="workflow-pill workflow-pill--approved"
          onClick={goActionCentre}
        >
          <span className="workflow-pill__num">{metrics.approved.toLocaleString()}</span>
          <span className="workflow-pill__label">Approved</span>
        </button>
        <span className="workflow-pill__arrow" aria-hidden="true" />
        <button
          type="button"
          className="workflow-pill workflow-pill--done"
          onClick={goActionCentre}
        >
          <span className="workflow-pill__num">{metrics.executed.toLocaleString()}</span>
          <span className="workflow-pill__label">Executed (30d)</span>
        </button>
        <Link
          to="/action-centre?hasAction=1"
          className="btn btn-primary findings-summary__cta"
        >
          Review {metrics.proposed.toLocaleString()} proposed
        </Link>
      </div>
    </section>
  );
}

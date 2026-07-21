import React, { useMemo } from 'react';
import { MapPin } from 'lucide-react';
import { formatCurrency } from '../../utils/format';
import { extractRegionMigration } from '../../utils/pillarEvidence';
import {
  buildWhatIfComparisonRows,
  extractPerformanceMetricsFromFinding,
  impactDirectionClass,
  impactDirectionLabel,
  projectWhatIfCosts,
  resolveWhatIfMonthlyCost,
} from '../../utils/whatIfUtils';

const RISK_CLASS = {
  low: 'wiz-pill wiz-pill--ok',
  medium: 'wiz-pill wiz-pill--warn',
  high: 'wiz-pill',
  critical: 'wiz-pill',
};

function formatActionLabel(action) {
  if (!action) return '';
  return String(action).replace(/_/g, ' ');
}

export default function WhatIfScenarioPanel({
  scenario,
  currency = 'CAD',
  monthlyCost = 0,
  finding = null,
}) {
  const resolvedMonthlyCost = resolveWhatIfMonthlyCost({ monthlyResourceCost: monthlyCost, finding });
  const findingSavings = finding?.estimated_savings_usd || 0;
  const performanceMetrics = extractPerformanceMetricsFromFinding(finding);
  const risk = String(scenario?.risk || 'low').toLowerCase();

  const costs = useMemo(
    () => (scenario ? projectWhatIfCosts({
      scenario,
      monthlyCost: resolvedMonthlyCost,
      findingSavings,
      currency,
    }) : null),
    [scenario, resolvedMonthlyCost, findingSavings, currency],
  );

  const comparisonRows = useMemo(
    () => (scenario ? buildWhatIfComparisonRows({
      scenario,
      monthlyCost: resolvedMonthlyCost,
      findingSavings,
      currency,
      performanceMetrics,
    }) : []),
    [scenario, resolvedMonthlyCost, findingSavings, currency, performanceMetrics],
  );

  if (!scenario) return null;

  const regionMigration = extractRegionMigration(finding?.evidence, scenario);
  const currentRegion = scenario.currentState?.region || regionMigration?.currentRegion;
  const targetRegion = scenario.recommendedTargetRegionDisplay
    || scenario.proposedState?.region
    || regionMigration?.recommendedRegionDisplay;

  return (
    <section className="wiz-whatif" style={{ marginTop: '0.75rem' }}>
      <header className="wiz-whatif__head">
        <div>
          <div className="wiz-impact-banner__label" style={{ marginBottom: 4 }}>What-if analysis</div>
          <strong style={{ fontSize: '0.92rem' }}>{scenario.title}</strong>
        </div>
        {scenario.action && (
          <span className={`wiz-whatif__action-badge ${RISK_CLASS[risk] || ''}`}>
            {formatActionLabel(scenario.action)}
          </span>
        )}
      </header>
      <div style={{ padding: '1rem' }}>
        {targetRegion && (
          <div className="finding-evidence__region-banner wiz-whatif__region" role="note">
            <div className="finding-evidence__section-label">
              <MapPin size={12} aria-hidden style={{ marginRight: 4, verticalAlign: -1 }} />
              Target region
            </div>
            {currentRegion ? (
              <p className="finding-evidence__region-line">
                <span className="finding-evidence__region-from">{currentRegion}</span>
                <span className="finding-evidence__region-arrow" aria-hidden>→</span>
                <span className="finding-evidence__region-to">{targetRegion}</span>
              </p>
            ) : (
              <p className="finding-evidence__region-line">
                Migrate to <strong>{targetRegion}</strong>
              </p>
            )}
          </div>
        )}

        {scenario.summary && (
          <p style={{ margin: '0 0 0.85rem', color: 'var(--text2)', fontSize: '0.85rem', lineHeight: 1.45 }}>
            {scenario.summary}
          </p>
        )}

        <div className="wiz-whatif__impact-table-wrap">
          <table className="wiz-whatif__impact-table">
            <thead>
              <tr>
                <th scope="col">Dimension</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
                <th scope="col">Change</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.label}</th>
                  <td>{row.before}</td>
                  <td className="wiz-whatif__after-cell">{row.after}</td>
                  <td>
                    <span className={`wiz-whatif__direction ${impactDirectionClass(row.direction)}`}>
                      {impactDirectionLabel(row.direction)}
                    </span>
                    {row.detail && (
                      <span className="wiz-whatif__impact-detail">{row.detail}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="wiz-whatif__compare">
          <div className="wiz-whatif__state">
            <label>Current state</label>
            {scenario.currentState?.description || '—'}
            {currentRegion && (
              <span className="wiz-whatif__state-region">Region: {currentRegion}</span>
            )}
          </div>
          <div className="wiz-whatif__arrow" aria-hidden>→</div>
          <div className="wiz-whatif__state wiz-whatif__state--proposed">
            <label>Proposed state</label>
            {scenario.proposedState?.description || '—'}
            {targetRegion && (
              <span className="wiz-whatif__state-region">Region: {targetRegion}</span>
            )}
          </div>
        </div>

        <div className="wiz-detail__meta-grid">
          <div className="wiz-meta-item">
            <label>Est. savings/mo</label>
            <span className="wiz-savings-cell wiz-savings-cell--positive">
              {costs.savings > 0 ? formatCurrency(costs.savings, { currency, decimals: 0 }) : '—'}
            </span>
          </div>
          <div className="wiz-meta-item">
            <label>Reversible</label>
            <span>{scenario.reversible ? 'Yes' : 'No'}</span>
          </div>
          <div className="wiz-meta-item">
            <label>Risk</label>
            <span>{risk}</span>
          </div>
          <div className="wiz-meta-item">
            <label>Blast radius</label>
            <span>{scenario.blastRadius || '—'}</span>
          </div>
        </div>

        {scenario.prerequisites?.length > 0 && (
          <div style={{ marginTop: '0.85rem' }}>
            <strong style={{ fontSize: '0.82rem' }}>Before you apply this change</strong>
            <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.1rem', fontSize: '0.82rem', color: 'var(--text2)' }}>
              {scenario.prerequisites.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

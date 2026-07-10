import React, { useMemo } from 'react';
import { Flame, Sparkles, Info, CheckCircle2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import PageHero from '../layout/PageHero';
import { formatCurrency } from '../../utils/format';
import { toDisplayText } from '../../utils/formatDisplay';
import { SAVINGS_SCOPE, SAVINGS_METRIC_SUB } from '../../config/savingsScope';

const SEVERITY_SEGMENTS = [
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
  { key: 'info', label: 'Info' },
];

function WasteWorkflowSteps({ hasFindings }) {
  const steps = [
    {
      id: 'sync',
      label: 'Sync findings',
      detail: hasFindings ? 'Idle findings loaded' : 'Run optimization analysis',
      done: hasFindings,
    },
    {
      id: 'explore',
      label: 'Explore heatmap',
      detail: 'Click cells to filter by category and severity',
      done: hasFindings,
    },
    {
      id: 'remediate',
      label: 'Review and act',
      detail: 'Click a row to review the finding summary',
      done: false,
    },
  ];

  return (
    <div className="waste-workflow" aria-label="How to use the waste heatmap">
      {steps.map((step, index) => (
        <React.Fragment key={step.id}>
          <div className={`waste-workflow__step${step.done ? ' waste-workflow__step--done' : ''}`}>
            <span className="waste-workflow__index" aria-hidden>
              {step.done ? <CheckCircle2 size={14} /> : index + 1}
            </span>
            <div className="waste-workflow__text">
              <strong>{step.label}</strong>
              <span>{step.detail}</span>
            </div>
          </div>
          {index < steps.length - 1 && <div className="waste-workflow__connector" aria-hidden />}
        </React.Fragment>
      ))}
    </div>
  );
}

function SeverityStrip({ bySeverity, total, activeSeverity, onSeverityClick }) {
  if (!total) {
    return (
      <div className="waste-hero__severity-strip waste-hero__severity-strip--empty">
        <span>No findings to chart yet</span>
      </div>
    );
  }

  return (
    <div
      className="waste-hero__severity-strip"
      role="group"
      aria-label="Findings distribution by severity"
    >
      {SEVERITY_SEGMENTS.map(({ key, label }) => {
        const count = bySeverity?.[key] ?? 0;
        if (!count) return null;
        const pct = (count / total) * 100;
        return (
          <button
            key={key}
            type="button"
            className={`waste-hero__severity-seg waste-hero__severity-seg--${key}${activeSeverity === key ? ' waste-hero__severity-seg--active' : ''}`}
            style={{ flexGrow: count, flexBasis: `${pct}%` }}
            title={`${label}: ${count.toLocaleString()} — click to filter`}
            aria-label={`${label}: ${count.toLocaleString()}`}
            onClick={() => onSeverityClick?.(key)}
            aria-pressed={activeSeverity === key}
          >
            {pct >= 10 && (
              <span className="waste-hero__severity-seg-label">{label.slice(0, 1)} {count.toLocaleString()}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function HotspotBadge({ category, count, savings, active, onClick }) {
  if (!category) return null;
  return (
    <button
      type="button"
      className={`waste-hero__hotspot${active ? ' waste-hero__hotspot--active' : ''}`}
      onClick={onClick}
      aria-pressed={active}
      aria-label={`Filter by hottest category: ${category}`}
    >
      <Sparkles size={14} aria-hidden className="waste-hero__hotspot-icon" />
      <div className="waste-hero__hotspot-text">
        <span className="waste-hero__hotspot-label">Top category</span>
        <strong>{category}</strong>
        <span className="waste-hero__hotspot-meta">
          {count.toLocaleString()} findings
          {savings > 0 ? ` · ${formatCurrency(savings, { currency: 'USD', decimals: 0 })} est.` : ''}
        </span>
      </div>
    </button>
  );
}

/**
 * Gradient hero band for the waste heatmap — KPIs, workflow, severity mix, and hotspots.
 */
export default function WasteHeatmapHero({
  subscriptionLabel,
  sweep,
  summary,
  loading,
  activeSeverity,
  activeCategory,
  onSeverityClick,
  onCategoryClick,
}) {
  const total = sweep?.total_idle_findings ?? 0;
  const totalSavings = sweep?.total_estimated_savings_usd ?? 0;
  const withSavings = sweep?.findings_with_savings ?? summary?.findings_with_savings ?? 0;
  const mostCommon = summary?.most_common_rule;

  const hotspot = useMemo(() => {
    const cats = sweep?.by_category;
    if (!cats || !Object.keys(cats).length) return null;
    const [category, count] = Object.entries(cats).sort((a, b) => b[1] - a[1])[0];
    const savings = sweep?.by_category_savings?.[category] ?? 0;
    return { category, count, savings };
  }, [sweep]);

  const subtitle = useMemo(() => {
    if (!total) {
      return 'Spot idle and orphaned resources by category and severity — then drill into findings to act.';
    }
    const parts = [];
    if (subscriptionLabel) parts.push(toDisplayText(subscriptionLabel));
    parts.push(`${total.toLocaleString()} idle findings from stored analysis`);
    if (mostCommon?.title || mostCommon?.rule_id) {
      parts.push(`top rule: ${mostCommon.title ?? mostCommon.rule_id}`);
    }
    return parts.join(' · ');
  }, [subscriptionLabel, total, mostCommon]);

  return (
    <PageHero
      variant="waste-heatmap-hero"
      eyebrow="Cost insights"
      title="Waste heatmap"
      subtitle={subtitle}
      scopeNote={SAVINGS_SCOPE.wasteHeatmap}
      isLoading={loading && !sweep}
      metrics={[
        {
          label: 'Open findings',
          value: total.toLocaleString(),
          tone: total > 0 ? 'warning' : 'default',
          sub: 'idle or orphaned',
        },
        {
          label: 'Idle & waste savings',
          value: sweep
            ? formatCurrency(totalSavings, { currency: 'USD', decimals: 0 })
            : '—',
          tone: totalSavings > 0 ? 'success' : 'default',
          featured: true,
          sub: SAVINGS_METRIC_SUB.waste,
        },
        {
          label: 'Critical',
          value: (sweep?.by_severity?.critical ?? 0).toLocaleString(),
          tone: 'danger',
          sub: 'needs attention',
        },
        {
          label: 'With savings est.',
          value: total > 0 ? withSavings.toLocaleString() : '—',
          tone: withSavings > 0 ? 'default' : 'default',
          sub: total > 0 ? `of ${total.toLocaleString()} findings` : 'after cost sync',
        },
      ]}
      actions={[
        { id: 'hub', label: 'Optimization hub', href: '/optimization-hub' },
        { id: 'history', label: 'Run history', href: '/history' },
        { id: 'costs', label: 'Cost explorer', href: '/costs' },
      ]}
      footer={(
        <div className="waste-hero__footer">
          <div className="waste-hero__footer-block waste-hero__footer-block--workflow">
            <span className="waste-hero__footer-label">
              <Flame size={14} aria-hidden />
              Workflow
            </span>
            <WasteWorkflowSteps hasFindings={total > 0} />
          </div>
          <div className="waste-hero__footer-grid">
            <div className="waste-hero__footer-block">
              <span className="waste-hero__footer-label">
                <Flame size={14} aria-hidden />
                Severity mix — click to filter
              </span>
              <SeverityStrip
                bySeverity={sweep?.by_severity}
                total={total}
                activeSeverity={activeSeverity}
                onSeverityClick={onSeverityClick}
              />
              <div className="waste-hero__severity-legend">
                {SEVERITY_SEGMENTS.map(({ key, label }) => {
                  const count = sweep?.by_severity?.[key] ?? 0;
                  if (!count) return null;
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`waste-hero__legend-item waste-hero__legend-item--${key}${activeSeverity === key ? ' waste-hero__legend-item--active' : ''}`}
                      onClick={() => onSeverityClick?.(key)}
                    >
                      {label} {count.toLocaleString()}
                    </button>
                  );
                })}
              </div>
            </div>
            <HotspotBadge
              category={hotspot?.category}
              count={hotspot?.count ?? 0}
              savings={hotspot?.savings ?? 0}
              active={activeCategory === hotspot?.category}
              onClick={() => hotspot?.category && onCategoryClick?.(hotspot.category)}
            />
          </div>
        </div>
      )}
    />
  );
}

export function WasteHeatmapDataNote({ sweep, summary }) {
  if (!sweep) return null;

  const total = sweep.total_idle_findings ?? 0;
  const returned = sweep.items_returned ?? sweep.idle_resources?.length ?? 0;
  const truncated = sweep.items_truncated;
  const withSavings = sweep.findings_with_savings ?? summary?.findings_with_savings ?? 0;
  const noSavings = total > 0 && (sweep.total_estimated_savings_usd ?? 0) <= 0;

  const notes = [];
  notes.push(
    'Counts come from open optimization findings matched to idle or waste rules. Charts and the heatmap use full subscription totals.',
  );
  if (noSavings) {
    notes.push(
      'Savings show as $0 until cost data is synced and optimization analysis is re-run.',
    );
  } else if (withSavings < total) {
    notes.push(
      `${(total - withSavings).toLocaleString()} findings do not have a savings estimate yet.`,
    );
  }
  if (truncated) {
    notes.push(
      `The table shows ${returned.toLocaleString()} of ${total.toLocaleString()} rows. Charts use the full dataset.`,
    );
  }

  return (
    <aside className="waste-data-note" aria-label="How waste heatmap data is calculated">
      <Info size={15} aria-hidden className="waste-data-note__icon" />
      <div className="waste-data-note__body">
        {notes.map((text) => (
          <p key={text}>{text}</p>
        ))}
      </div>
    </aside>
  );
}

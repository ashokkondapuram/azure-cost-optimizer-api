import React, { useMemo } from 'react';
import { AlertTriangle, CheckCircle2, Gauge, Layers } from 'lucide-react';
import PageHero from '../layout/PageHero';
import { toDisplayText } from '../../utils/formatDisplay';

const SOURCE_SEGMENTS = [
  { key: 'compute', label: 'Compute', tone: 'sky' },
  { key: 'network', label: 'Network', tone: 'teal' },
  { key: 'storage', label: 'Storage', tone: 'amber' },
];

function WorkflowSteps({ hasData }) {
  const steps = [
    {
      id: 'region',
      label: 'Pick a region',
      detail: hasData ? 'Quota loaded for selected region(s)' : 'Choose a region or scan all deployed regions',
      done: hasData,
    },
    {
      id: 'review',
      label: 'Review limits',
      detail: 'Sort and filter by category or status',
      done: hasData,
    },
    {
      id: 'act',
      label: 'Plan capacity',
      detail: 'Request increases before deployments hit limits',
      done: false,
    },
  ];

  return (
    <div className="quota-workflow" aria-label="How to use quota usage">
      {steps.map((step, index) => (
        <React.Fragment key={step.id}>
          <div className={`quota-workflow__step${step.done ? ' quota-workflow__step--done' : ''}`}>
            <span className="quota-workflow__index" aria-hidden>
              {step.done ? <CheckCircle2 size={14} /> : index + 1}
            </span>
            <div className="quota-workflow__text">
              <strong>{step.label}</strong>
              <span>{step.detail}</span>
            </div>
          </div>
          {index < steps.length - 1 && <div className="quota-workflow__connector" aria-hidden />}
        </React.Fragment>
      ))}
    </div>
  );
}

function CategoryStrip({ bySource, total, activeSource, onSourceClick }) {
  if (!total) {
    return (
      <div className="quota-hero__source-strip quota-hero__source-strip--empty">
        <span>No quota data to chart yet</span>
      </div>
    );
  }

  return (
    <div className="quota-hero__source-strip" role="group" aria-label="Quota by category">
      {SOURCE_SEGMENTS.map(({ key, label, tone }) => {
        const count = bySource?.[key] ?? 0;
        if (!count) return null;
        const pct = (count / total) * 100;
        return (
          <button
            key={key}
            type="button"
            className={[
              'quota-hero__source-seg',
              `quota-hero__source-seg--${tone}`,
              activeSource === key ? 'quota-hero__source-seg--active' : '',
            ].filter(Boolean).join(' ')}
            style={{ flexGrow: count, flexBasis: `${pct}%` }}
            title={`${label}: ${count.toLocaleString()} — click to filter`}
            aria-label={`${label}: ${count.toLocaleString()}`}
            onClick={() => onSourceClick?.(key)}
            aria-pressed={activeSource === key}
          >
            {pct >= 12 && (
              <span className="quota-hero__source-seg-label">
                {label} {count.toLocaleString()}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function QuotaDataNote({ mode, locationLabel }) {
  return (
    <aside className="quota-data-note" aria-label="How quota data is sourced">
      <Gauge size={15} aria-hidden className="quota-data-note__icon" />
      <div className="quota-data-note__body">
        <p>
          Quota usage is fetched live from Azure for your subscription
          {locationLabel ? ` in ${locationLabel}` : ''}.
          Limits apply per region — use &quot;All deployed regions&quot; to scan every region where you have resources.
          {mode === 'all_regions' && ' Showing merged results across regions.'}
        </p>
      </div>
    </aside>
  );
}

export default function QuotaUsageHero({
  subscriptionLabel,
  payload,
  loading,
  activeSource,
  onSourceClick,
  locationLabel,
}) {
  const items = payload?.items ?? [];
  const total = items.length;
  const bySource = useMemo(() => {
    const counts = { compute: 0, network: 0, storage: 0 };
    for (const item of items) {
      if (item.source in counts) counts[item.source] += 1;
    }
    return counts;
  }, [items]);

  const subtitle = useMemo(() => {
    const parts = [];
    if (subscriptionLabel) parts.push(toDisplayText(subscriptionLabel));
    if (locationLabel) parts.push(locationLabel);
    if (total) parts.push(`${total.toLocaleString()} quota types`);
    else if (!loading) parts.push('Select a region to load quotas');
    if (payload?.critical_count) {
      parts.push(`${payload.critical_count} critical`);
    } else if (payload?.near_limit_count) {
      parts.push(`${payload.near_limit_count} near limit`);
    }
    return parts.join(' · ');
  }, [subscriptionLabel, locationLabel, total, loading, payload]);

  return (
    <PageHero
      variant="quota-hero"
      eyebrow="Operations"
      title="Quota usage"
      subtitle={subtitle}
      isLoading={loading && !payload}
      metrics={[
        {
          label: 'Quota types',
          value: payload ? total.toLocaleString() : '—',
          tone: total > 0 ? 'default' : 'default',
          sub: locationLabel || 'per region',
        },
        {
          label: 'Critical',
          value: payload ? (payload.critical_count ?? 0).toLocaleString() : '—',
          tone: (payload?.critical_count ?? 0) > 0 ? 'danger' : 'default',
          featured: (payload?.critical_count ?? 0) > 0,
          sub: '≥ 95% used',
        },
        {
          label: 'Near limit',
          value: payload ? (payload.near_limit_count ?? 0).toLocaleString() : '—',
          tone: (payload?.near_limit_count ?? 0) > 0 ? 'warning' : 'default',
          sub: '≥ 80% used',
        },
        {
          label: 'Healthy',
          value: payload ? (payload.totals?.ok ?? items.filter((i) => i.status === 'ok').length).toLocaleString() : '—',
          tone: 'default',
          sub: 'under 80%',
        },
      ]}
      actions={[
        { id: 'actions', label: 'Action centre', href: '/action-centre' },
        { id: 'vms', label: 'Virtual machines', href: '/action-centre?resourceType=vms' },
        { id: 'hub', label: 'Proposed actions', href: '/action-centre?hasAction=1' },
      ]}
      footer={(
        <div className="quota-hero__footer">
          <div className="quota-hero__footer-block quota-hero__footer-block--workflow">
            <WorkflowSteps hasData={total > 0} />
          </div>
          <div className="quota-hero__footer-grid">
            <div className="quota-hero__footer-block">
              <span className="quota-hero__footer-label">
                <Layers size={13} aria-hidden />
                By category
              </span>
              <CategoryStrip
                bySource={bySource}
                total={total}
                activeSource={activeSource}
                onSourceClick={onSourceClick}
              />
            </div>
            {(payload?.critical_count > 0 || payload?.near_limit_count > 0) && (
              <div className="quota-hero__footer-block">
                <div className="quota-hero__alert">
                  <AlertTriangle size={14} aria-hidden />
                  <div>
                    <strong>Capacity attention needed</strong>
                    <span>
                      {(payload.critical_count ?? 0) > 0
                        ? `${payload.critical_count} quota type${payload.critical_count !== 1 ? 's are' : ' is'} at critical levels.`
                        : `${payload.near_limit_count} quota type${payload.near_limit_count !== 1 ? 's are' : ' is'} nearing limits.`}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    />
  );
}

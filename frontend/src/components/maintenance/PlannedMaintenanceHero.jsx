import React, { useMemo } from 'react';
import { CheckCircle2, Clock, Layers } from 'lucide-react';
import PageHero from '../layout/PageHero';
import AssetIcon from '../AssetIcon';
import { toDisplayText } from '../../utils/formatDisplay';
import { formatDateTime, formatDateTimeUtc } from '../../utils/format';
import { MAINTENANCE_SOURCE_ICON, maintenanceCategory } from '../../utils/maintenanceUtils';

const SOURCE_SEGMENTS = [
  { key: 'health_event', label: 'Service health', tone: 'amber', iconKey: MAINTENANCE_SOURCE_ICON.health_event },
  { key: 'vm', label: 'Virtual machines', tone: 'sky', iconKey: MAINTENANCE_SOURCE_ICON.vm },
  { key: 'vmss', label: 'VM scale sets', tone: 'teal', iconKey: MAINTENANCE_SOURCE_ICON.vmss },
  { key: 'vmss_instance', label: 'VMSS instances', tone: 'violet', iconKey: MAINTENANCE_SOURCE_ICON.vmss_instance },
];

function WorkflowSteps({ hasData }) {
  const steps = [
    {
      id: 'load',
      label: 'Load maintenance',
      detail: hasData ? 'Cached maintenance data loaded' : 'Refresh to sync from Azure',
      done: hasData,
    },
    {
      id: 'filter',
      label: 'Filter by type',
      detail: 'Use the type strip or filters below',
      done: hasData,
    },
    {
      id: 'plan',
      label: 'Plan around windows',
      detail: 'Review timelines before change windows',
      done: false,
    },
  ];

  return (
    <div className="maintenance-workflow" aria-label="How to use planned maintenance">
      {steps.map((step, index) => (
        <React.Fragment key={step.id}>
          <div className={`maintenance-workflow__step${step.done ? ' maintenance-workflow__step--done' : ''}`}>
            <span className="maintenance-workflow__index" aria-hidden>
              {step.done ? <CheckCircle2 size={14} /> : index + 1}
            </span>
            <div className="maintenance-workflow__text">
              <strong>{step.label}</strong>
              <span>{step.detail}</span>
            </div>
          </div>
          {index < steps.length - 1 && <div className="maintenance-workflow__connector" aria-hidden />}
        </React.Fragment>
      ))}
    </div>
  );
}

function SourceStrip({ bySource, total, activeSource, onSourceClick }) {
  if (!total) {
    return (
      <div className="maintenance-hero__source-strip maintenance-hero__source-strip--empty">
        <span>No maintenance items to chart yet</span>
      </div>
    );
  }

  return (
    <div className="maintenance-hero__source-strip" role="group" aria-label="Maintenance by type">
      {SOURCE_SEGMENTS.map(({ key, label, tone, iconKey }) => {
        const count = bySource?.[key] ?? 0;
        if (!count) return null;
        const pct = (count / total) * 100;
        return (
          <button
            key={key}
            type="button"
            className={[
              'maintenance-hero__source-seg',
              `maintenance-hero__source-seg--${tone}`,
              activeSource === key ? 'maintenance-hero__source-seg--active' : '',
            ].filter(Boolean).join(' ')}
            style={{ flexGrow: count, flexBasis: `${pct}%` }}
            title={`${label}: ${count.toLocaleString()} — click to filter`}
            aria-label={`${label}: ${count.toLocaleString()}`}
            onClick={() => onSourceClick?.(key)}
            aria-pressed={activeSource === key}
          >
            {pct >= 12 && (
              <span className="maintenance-hero__source-seg-label">
                <AssetIcon iconKey={iconKey} size={12} alt="" className="maintenance-hero__source-seg-icon" />
                {label.split(' ')[0]} {count.toLocaleString()}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function NextWindowBadge({ item }) {
  if (!item) return null;
  return (
    <div className="maintenance-hero__next">
      <Clock size={14} aria-hidden className="maintenance-hero__next-icon" />
      <div className="maintenance-hero__next-text">
        <span className="maintenance-hero__next-label">Next window</span>
        <strong>{item.resource_name}</strong>
        <span className="maintenance-hero__next-meta">
          {item.window_start ? formatDateTimeUtc(item.window_start) : item.title}
        </span>
      </div>
    </div>
  );
}

export function PlannedMaintenanceDataNote({ syncedAt, dataSource }) {
  const syncLabel = syncedAt ? formatDateTime(syncedAt) : null;
  return (
    <aside className="maintenance-data-note" aria-label="How planned maintenance data is sourced">
      <AssetIcon iconKey="updates" size={15} alt="" className="maintenance-data-note__icon" />
      <div className="maintenance-data-note__body">
        <p>
          Data is synced from Azure every 2 hours and served from the database.
          VM and VMSS platform windows come from Compute APIs; VMSS maintenance
          also appears in activity logs (live migration, redeploy, upgrades) because
          it is not always listed in Service Health.
          {syncLabel && (
            <>
              {' '}Last updated {syncLabel}
              {dataSource === 'database' ? ' (cached)' : ' (live sync)'}.
            </>
          )}
        </p>
      </div>
    </aside>
  );
}

export default function PlannedMaintenanceHero({
  subscriptionLabel,
  payload,
  summary,
  loading,
  activeSource,
  onSourceClick,
  nextItem,
}) {
  const total = payload?.count ?? 0;
  const bySource = useMemo(() => {
    const counts = { health_event: 0, vm: 0, vmss: 0, vmss_instance: 0 };
    for (const item of payload?.items ?? []) {
      const key = maintenanceCategory(item);
      if (key in counts) counts[key] += 1;
    }
    return counts;
  }, [payload?.items]);

  const subtitle = useMemo(() => {
    const parts = [];
    if (subscriptionLabel) parts.push(toDisplayText(subscriptionLabel));
    if (total) {
      parts.push(`${total.toLocaleString()} upcoming maintenance items`);
    } else if (!loading) {
      parts.push('No upcoming maintenance windows found');
    }
    if (nextItem?.window_start) {
      parts.push(`next: ${formatDateTimeUtc(nextItem.window_start)}`);
    }
    return parts.join(' · ');
  }, [subscriptionLabel, total, loading, nextItem]);

  return (
    <PageHero
      variant="maintenance-hero"
      eyebrow="Operations"
      title="Planned maintenance"
      subtitle={subtitle}
      isLoading={loading && !payload}
      metrics={[
        {
          label: 'Total items',
          value: payload ? total.toLocaleString() : '—',
          tone: total > 0 ? 'warning' : 'default',
          sub: 'upcoming only',
        },
        {
          label: 'Virtual machines',
          value: payload ? (summary?.vms ?? 0).toLocaleString() : '—',
          tone: (summary?.vms ?? 0) > 0 ? 'default' : 'default',
          featured: (summary?.vms ?? 0) > 0,
          sub: 'platform windows',
        },
        {
          label: 'VM scale sets',
          value: payload
            ? ((summary?.vmss ?? 0) + (summary?.vmss_instances ?? 0)).toLocaleString()
            : '—',
          tone: 'default',
          sub: 'sets and instances',
        },
        {
          label: 'Service health',
          value: payload ? (summary?.health_events ?? 0).toLocaleString() : '—',
          tone: (summary?.health_events ?? 0) > 0 ? 'danger' : 'default',
          sub: 'planned events',
        },
      ]}
      actions={[
        { id: 'vms', label: 'Virtual machines', href: '/action-centre?resourceType=vms' },
        { id: 'aks', label: 'AKS clusters', href: '/action-centre?resourceType=aks' },
        { id: 'hub', label: 'Proposed actions', href: '/action-centre?hasAction=1' },
      ]}
      footer={(
        <div className="maintenance-hero__footer">
          <div className="maintenance-hero__footer-block maintenance-hero__footer-block--workflow">
            <WorkflowSteps hasData={total > 0} />
          </div>
          <div className="maintenance-hero__footer-grid">
            <div className="maintenance-hero__footer-block">
              <span className="maintenance-hero__footer-label">
                <Layers size={13} aria-hidden />
                By type
              </span>
              <SourceStrip
                bySource={bySource}
                total={total}
                activeSource={activeSource}
                onSourceClick={onSourceClick}
              />
            </div>
            <div className="maintenance-hero__footer-block">
              <NextWindowBadge item={nextItem} />
            </div>
          </div>
        </div>
      )}
    />
  );
}

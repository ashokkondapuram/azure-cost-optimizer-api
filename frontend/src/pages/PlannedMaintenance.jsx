/**
 * Planned maintenance — VMs, VMSS, and Azure service health events.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronDown, ChevronUp, Clock, X,
} from 'lucide-react';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import PlannedMaintenanceHero, { PlannedMaintenanceDataNote } from '../components/maintenance/PlannedMaintenanceHero';
import FilterBar from '../components/FilterBar';
import AssetIcon from '../components/AssetIcon';
import { AdvEmptyState, AdvSkeleton } from '../components/advanced/AdvUI';
import { fetchPlannedMaintenance } from '../api/maintenance';
import { formatDateTime, formatDateTimeUtc, formatIsoDate } from '../utils/format';
import {
  CATEGORY_OPTIONS,
  URGENCY_LABEL,
  categoryLabel,
  findNextMaintenanceWindow,
  formatMaintenanceWindow,
  groupMaintenanceByResource,
  iconKeyForMaintenanceItem,
  isUpcomingWindow,
  maintenanceCategory,
  timelineDateLabel,
  urgencyFor,
} from '../utils/maintenanceUtils';

const TYPE_OPTIONS = CATEGORY_OPTIONS;

function MaintenanceMetaStrip({ nextItem, summary }) {
  const items = [
    nextItem?.window_start && {
      label: 'Next window',
      value: formatDateTimeUtc(nextItem.window_start),
    },
    summary?.vms != null && {
      label: 'VMs',
      value: summary.vms.toLocaleString(),
    },
    summary?.health_events != null && {
      label: 'Service health',
      value: summary.health_events.toLocaleString(),
    },
  ].filter(Boolean);

  if (!items.length) return null;

  return (
    <div className="maintenance-meta-strip" aria-label="Maintenance summary">
      {items.map((item) => (
        <span key={item.label} className="maintenance-meta-strip__chip">
          <span className="maintenance-meta-strip__label">{item.label}</span>
          <span className="maintenance-meta-strip__value">{item.value}</span>
        </span>
      ))}
    </div>
  );
}

function PlannedMaintenanceEmptyIcon({ size = 22 }) {
  return <AssetIcon iconKey="updates" size={size} alt="" />;
}

function ResourceMaintenanceIcon({ group }) {
  const item = group.items[0];
  return (
    <span className="maintenance-resource__icon" aria-hidden>
      <AssetIcon
        resourceId={group.resource_id}
        iconKey={iconKeyForMaintenanceItem(item)}
        size={22}
        fallback={<AssetIcon iconKey="virtualMachine" size={22} alt="" />}
      />
    </span>
  );
}

function MaintenanceTimeline({ items, selectedId, onSelect }) {
  if (!items.length) return null;

  return (
    <section className="maintenance-section-card mb-5" aria-labelledby="maintenance-timeline-title">
      <div className="maintenance-section-card__head">
        <div>
          <h2 id="maintenance-timeline-title" className="maintenance-section-card__title">
            Upcoming timeline
          </h2>
          <p className="maintenance-section-card__sub">
            {items.length.toLocaleString()} upcoming window{items.length !== 1 ? 's' : ''} · UTC
          </p>
        </div>
      </div>
      <div className="maintenance-timeline">
        {items.map((item) => {
          const urgency = urgencyFor(item);
          return (
            <button
              key={item.id}
              type="button"
              className={[
                'maintenance-timeline__card',
                selectedId === item.id ? 'maintenance-timeline__card--selected' : '',
                `maintenance-timeline__card--${urgency}`,
              ].filter(Boolean).join(' ')}
              onClick={() => onSelect(item)}
              aria-pressed={selectedId === item.id}
            >
              <div className="maintenance-timeline__date">
                <Clock size={14} aria-hidden />
                <span>{timelineDateLabel(item)}</span>
              </div>
              <div className="maintenance-timeline__body">
                <span className={`maintenance-source-pill maintenance-source-pill--${maintenanceCategory(item)}`}>
                  {categoryLabel(item)}
                </span>
                <strong className="maintenance-timeline__name">{item.resource_name}</strong>
                <span className="maintenance-timeline__title">{item.title}</span>
              </div>
              <span className={`maintenance-urgency-pill maintenance-urgency-pill--${urgency}`}>
                {URGENCY_LABEL[urgency]}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function MaintenanceByResource({ groups, loading, selectedId, onSelect, listRef }) {
  const [sortKey, setSortKey] = useState('resource');
  const [sortDir, setSortDir] = useState('asc');

  const sortedGroups = useMemo(() => {
    if (!groups?.length) return [];
    return [...groups].sort((a, b) => {
      let av;
      let bv;
      if (sortKey === 'resource') {
        av = a.resource_name || '';
        bv = b.resource_name || '';
      } else if (sortKey === 'count') {
        av = a.items.length;
        bv = b.items.length;
      } else {
        av = a.items[0]?.window_start || '9999';
        bv = b.items[0]?.window_start || '9999';
      }
      if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  }, [groups, sortKey, sortDir]);

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
  }

  if (loading) return <AdvSkeleton className="h-56 rounded-xl" />;

  return (
    <section ref={listRef} className="maintenance-section-card" aria-labelledby="maintenance-resources-title">
      <div className="maintenance-section-card__head maintenance-section-card__head--row">
        <div>
          <h2 id="maintenance-resources-title" className="maintenance-section-card__title">
            By resource
          </h2>
          <p className="maintenance-section-card__sub">
            {sortedGroups.length.toLocaleString()} resource{sortedGroups.length !== 1 ? 's' : ''} · Click an event for details
          </p>
        </div>
        <div className="maintenance-resource-sort" role="group" aria-label="Sort resources">
          {[
            { key: 'resource', label: 'Name' },
            { key: 'window_start', label: 'Next window' },
            { key: 'count', label: 'Events' },
          ].map((col) => (
            <button
              key={col.key}
              type="button"
              className={`maintenance-resource-sort__btn${sortKey === col.key ? ' maintenance-resource-sort__btn--active' : ''}`}
              onClick={() => toggleSort(col.key)}
            >
              {col.label}
              {sortKey === col.key && (sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
            </button>
          ))}
        </div>
      </div>

      {!sortedGroups.length ? (
        <AdvEmptyState
          title="No planned maintenance found"
          description="Azure did not return upcoming maintenance for VMs, VMSS, or service health in this subscription."
          icon={PlannedMaintenanceEmptyIcon}
        />
      ) : (
        <div className="maintenance-resource-list">
          {sortedGroups.map((group) => (
            <article key={group.key} className="maintenance-resource">
              <header className="maintenance-resource__head">
                <ResourceMaintenanceIcon group={group} />
                <div className="maintenance-resource__meta">
                  <strong className="maintenance-resource__name">{group.resource_name}</strong>
                  <span className="maintenance-resource__sub">
                    {[group.resource_group, group.location, group.resource_type]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </div>
                <span className="maintenance-resource__count">
                  {group.items.length} event{group.items.length !== 1 ? 's' : ''}
                </span>
              </header>
              <ul className="maintenance-resource__events">
                {group.items.map((item) => {
                  const urgency = urgencyFor(item);
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={[
                          'maintenance-resource__event',
                          selectedId === item.id ? 'maintenance-resource__event--selected' : '',
                        ].filter(Boolean).join(' ')}
                        onClick={() => onSelect(item)}
                        aria-pressed={selectedId === item.id}
                      >
                        <div className="maintenance-resource__event-main">
                          <span className={`maintenance-source-pill maintenance-source-pill--${maintenanceCategory(item)}`}>
                            {categoryLabel(item)}
                          </span>
                          <strong>{item.title}</strong>
                          <span className="maintenance-resource__event-window">
                            {formatMaintenanceWindow(item.window_start, item.window_end)}
                          </span>
                        </div>
                        <span className={`maintenance-urgency-pill maintenance-urgency-pill--${urgency}`}>
                          {item.status || URGENCY_LABEL[urgency]}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function MaintenanceDetailPanel({ item, onClose }) {
  if (!item) return null;
  const urgency = urgencyFor(item);

  return (
    <aside className="maintenance-detail-panel card" aria-label="Maintenance details">
      <header className="maintenance-detail-panel__head">
        <div className="maintenance-detail-panel__head-main">
          <AssetIcon
            resourceId={item.resource_id}
            iconKey={iconKeyForMaintenanceItem(item)}
            size={24}
            fallback={<AssetIcon iconKey="virtualMachine" size={24} alt="" />}
          />
          <div>
            <p className="maintenance-detail-panel__eyebrow">{categoryLabel(item)}</p>
            <h3 className="maintenance-detail-panel__title">{item.resource_name}</h3>
          </div>
        </div>
        <button type="button" className="btn btn-ghost btn-icon-only" onClick={onClose} aria-label="Close details">
          <X size={16} />
        </button>
      </header>
      <div className="maintenance-detail-panel__body">
        <div className="maintenance-detail-panel__chips">
          <span className={`maintenance-source-pill maintenance-source-pill--${maintenanceCategory(item)}`}>
            {categoryLabel(item)}
          </span>
          <span className={`maintenance-urgency-pill maintenance-urgency-pill--${urgency}`}>
            {URGENCY_LABEL[urgency]}
          </span>
        </div>

        <div className="maintenance-detail-panel__window-card">
          <span className="maintenance-detail-panel__window-label">Maintenance window (UTC)</span>
          <strong>{formatMaintenanceWindow(item.window_start, item.window_end)}</strong>
          {item.title && <p>{item.title}</p>}
        </div>

        <dl className="maintenance-detail-panel__facts">
          <div className="maintenance-detail-panel__fact">
            <dt>Status</dt>
            <dd>{item.status || '—'}</dd>
          </div>
          {item.resource_group && (
            <div className="maintenance-detail-panel__fact">
              <dt>Resource group</dt>
              <dd>{item.resource_group}</dd>
            </div>
          )}
          {item.location && (
            <div className="maintenance-detail-panel__fact">
              <dt>Location</dt>
              <dd>{item.location}</dd>
            </div>
          )}
          {item.resource_type && (
            <div className="maintenance-detail-panel__fact">
              <dt>Type</dt>
              <dd className="maintenance-detail-panel__mono">{item.resource_type}</dd>
            </div>
          )}
        </dl>

        {item.detail && (
          <section className="maintenance-detail-panel__section">
            <h4>Details</h4>
            <p>{item.detail}</p>
          </section>
        )}
      </div>
    </aside>
  );
}

export default function PlannedMaintenance() {
  const { subscription, subscriptionLabel } = useAdvancedSubscription();
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sourceFilter, setSourceFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const listRef = React.useRef(null);

  const load = useCallback(async ({ forceRefresh = false } = {}) => {
    if (!subscription?.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPlannedMaintenance(subscription, {
        upcoming_only: true,
        force_refresh: forceRefresh,
      });
      setPayload(data);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setSelected(null);
    setSourceFilter('');
    setSearch('');
  }, [subscription]);

  const items = payload?.items ?? [];
  const summary = payload?.summary ?? {};

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (sourceFilter && maintenanceCategory(item) !== sourceFilter) return false;
      if (!q) return true;
      const hay = [
        item.resource_name,
        item.resource_group,
        item.title,
        item.status,
        item.detail,
        item.resource_type,
        categoryLabel(item),
      ].filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [items, sourceFilter, search]);

  const resourceGroups = useMemo(
    () => groupMaintenanceByResource(filteredItems),
    [filteredItems],
  );

  const timelineItems = useMemo(() => (
    filteredItems
      .filter((item) => isUpcomingWindow(item) && (item.window_start || item.pending_model_update || item.pending_model_updates))
      .sort((a, b) => (a.window_start || '9999').localeCompare(b.window_start || '9999'))
      .slice(0, 8)
  ), [filteredItems]);

  const nextItem = useMemo(
    () => findNextMaintenanceWindow(items),
    [items],
  );

  const handleSelect = useCallback((item) => {
    setSelected((current) => (current?.id === item.id ? null : item));
  }, []);

  const toggleSource = useCallback((source) => {
    setSourceFilter((current) => (current === source ? '' : source));
    setSelected(null);
  }, []);

  const hasFilters = !!(sourceFilter || search.trim());
  const isEmpty = !loading && !error && payload && items.length === 0;

  return (
    <AdvancedToolLayout
      title="Planned maintenance"
      subtitle="See upcoming platform maintenance for virtual machines, scale sets, and Azure service health events."
      iconKey="plannedMaintenance"
      iconRoute="/planned-maintenance"
      hasHeroBand
      metaItems={[
        payload?.count != null && `${payload.count.toLocaleString()} items`,
        payload?.synced_at && `Updated ${formatDateTime(payload.synced_at)}`,
        nextItem?.window_start && `Next ${formatIsoDate(nextItem.window_start.slice(0, 10))} UTC`,
      ].filter(Boolean)}
      onRefresh={() => load({ forceRefresh: true })}
      loading={loading}
      error={error}
      errorTitle="Could not load planned maintenance"
    >
      <PlannedMaintenanceHero
        subscriptionLabel={subscriptionLabel}
        payload={payload}
        summary={summary}
        loading={loading}
        activeSource={sourceFilter}
        onSourceClick={toggleSource}
        nextItem={nextItem}
      />

      <PlannedMaintenanceDataNote syncedAt={payload?.synced_at} dataSource={payload?.data_source} />

      {isEmpty ? (
        <AdvEmptyState
          title="No planned maintenance"
          description="There are no upcoming maintenance windows for VMs, VMSS, or service health in this subscription."
          icon={PlannedMaintenanceEmptyIcon}
        />
      ) : (
        <>
          <MaintenanceMetaStrip nextItem={nextItem} summary={summary} />

          <FilterBar
            className="maintenance-filter-bar mb-4"
            search={{
              value: search,
              onChange: setSearch,
              placeholder: 'Search resources, groups, or maintenance titles…',
            }}
            selects={[
              {
                id: 'source',
                label: 'Type',
                value: sourceFilter,
                onChange: (v) => { setSourceFilter(v); setSelected(null); },
                options: TYPE_OPTIONS,
              },
            ]}
            onClear={hasFilters ? () => { setSourceFilter(''); setSearch(''); setSelected(null); } : undefined}
            resultCount={{
              shown: filteredItems.length,
              total: items.length,
              label: 'items',
            }}
          />

          <MaintenanceTimeline
            items={timelineItems}
            selectedId={selected?.id}
            onSelect={handleSelect}
          />

          <div className={`maintenance-split${selected ? ' maintenance-split--open' : ''}`}>
            <MaintenanceByResource
              groups={resourceGroups}
              loading={loading}
              selectedId={selected?.id}
              onSelect={handleSelect}
              listRef={listRef}
            />
            <MaintenanceDetailPanel item={selected} onClose={() => setSelected(null)} />
          </div>
        </>
      )}
    </AdvancedToolLayout>
  );
}

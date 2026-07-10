/**
 * Subscription quota usage — compute, network, and storage limits per region.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Gauge, MapPin,
} from 'lucide-react';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import QuotaUsageHero, { QuotaDataNote } from '../components/quota/QuotaUsageHero';
import FilterBar from '../components/FilterBar';
import { AdvEmptyState, AdvSkeleton } from '../components/advanced/AdvUI';
import usePersistedState from '../hooks/usePersistedState';
import {
  fetchAllRegionsQuota,
  fetchQuotaLocations,
  fetchSubscriptionQuota,
} from '../api/quota';

const SOURCE_LABEL = {
  compute: 'Compute',
  network: 'Network',
  storage: 'Storage',
};

const SOURCE_OPTIONS = [
  { value: '', label: 'All categories' },
  { value: 'compute', label: 'Compute' },
  { value: 'network', label: 'Network' },
  { value: 'storage', label: 'Storage' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'critical', label: 'Critical (≥95%)' },
  { value: 'warning', label: 'Near limit (≥80%)' },
  { value: 'ok', label: 'Healthy' },
];

const STATUS_LABEL = {
  critical: 'Critical',
  warning: 'Near limit',
  ok: 'Healthy',
};

function formatRegionLabel(location, mode) {
  if (mode === 'all_regions') return 'All deployed regions';
  if (!location) return '';
  return location.replace(/([a-z])([0-9])/g, '$1 $2').replace(/\b\w/g, (c) => c.toUpperCase());
}

function UsageBar({ pct, status }) {
  const width = Math.min(Math.max(pct || 0, 0), 100);
  return (
    <div className={`quota-usage-bar quota-usage-bar--${status || 'ok'}`} aria-hidden>
      <span className="quota-usage-bar__fill" style={{ width: `${width}%` }} />
    </div>
  );
}

function NearLimitStrip({ items, onSelect, selectedId }) {
  const near = items.filter((i) => i.status === 'critical' || i.status === 'warning').slice(0, 6);
  if (!near.length) return null;

  return (
    <section className="quota-section-card mb-4" aria-labelledby="quota-near-limit-title">
      <div className="quota-section-card__head">
        <h2 id="quota-near-limit-title" className="quota-section-card__title">Needs attention</h2>
        <p className="quota-section-card__sub">
          {near.length.toLocaleString()} highest-risk quota{near.length !== 1 ? ' types' : ' type'}
        </p>
      </div>
      <div className="quota-near-limit-grid">
        {near.map((item) => (
          <button
            key={`${item.location || ''}:${item.name}:${item.source}`}
            type="button"
            className={[
              'quota-near-limit-card',
              `quota-near-limit-card--${item.status}`,
              selectedId === `${item.location || ''}:${item.name}` ? 'quota-near-limit-card--selected' : '',
            ].filter(Boolean).join(' ')}
            onClick={() => onSelect(item)}
          >
            <span className={`quota-source-pill quota-source-pill--${item.source}`}>
              {SOURCE_LABEL[item.source]}
            </span>
            <strong>{item.localized_name || item.name}</strong>
            <span className="quota-near-limit-card__meta">
              {item.current?.toLocaleString()} / {item.limit?.toLocaleString()} ({item.usage_pct}%)
            </span>
            {item.location && (
              <span className="quota-near-limit-card__region">{item.location}</span>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

function QuotaTable({ items, loading, selectedKey, onSelect, showRegion }) {
  const [sortKey, setSortKey] = useState('usage_pct');
  const [sortDir, setSortDir] = useState('desc');

  const sorted = useMemo(() => {
    if (!items?.length) return [];
    return [...items].sort((a, b) => {
      let av = a[sortKey];
      let bv = b[sortKey];
      if (sortKey === 'usage_pct' || sortKey === 'current' || sortKey === 'limit') {
        av = Number(av) || 0;
        bv = Number(bv) || 0;
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      av = av ?? '';
      bv = bv ?? '';
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  }, [items, sortKey, sortDir]);

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir(key === 'name' ? 'asc' : 'desc'); }
  }

  if (loading) return <AdvSkeleton className="h-56 rounded-xl" />;

  return (
    <section className="quota-section-card" aria-labelledby="quota-table-title">
      <div className="quota-section-card__head">
        <div>
          <h2 id="quota-table-title" className="quota-section-card__title">All quota types</h2>
          <p className="quota-section-card__sub">
            {sorted.length.toLocaleString()} limit{sorted.length !== 1 ? 's' : ''} · subscription-level caps per region
          </p>
        </div>
      </div>

      {!sorted.length ? (
        <AdvEmptyState
          title="No quota data"
          description="Choose a region and refresh to load Azure subscription quotas."
          icon={Gauge}
        />
      ) : (
        <div className="tag-rg-explorer__scroll">
          <table className="tag-rg-table quota-table">
            <thead>
              <tr>
                {[
                  ...(showRegion ? [{ key: 'location', label: 'Region' }] : []),
                  { key: 'name', label: 'Quota' },
                  { key: 'source', label: 'Category' },
                  { key: 'usage_pct', label: 'Usage' },
                  { key: 'current', label: 'Used' },
                  { key: 'limit', label: 'Limit' },
                  { key: 'status', label: 'Status' },
                ].map((col) => (
                  <th
                    key={col.key}
                    className={`tag-rg-table__th--sortable${sortKey === col.key ? ' tag-rg-table__th--active' : ''}`}
                    onClick={() => toggleSort(col.key)}
                  >
                    <span className="tag-rg-table__sort">
                      {col.label}
                      {sortKey === col.key && (sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((item) => {
                const rowKey = `${item.location || ''}:${item.name}`;
                return (
                  <tr
                    key={`${rowKey}:${item.source}`}
                    className={[
                      'tag-rg-table__row',
                      'quota-table__row',
                      selectedKey === rowKey ? 'quota-table__row--selected' : '',
                    ].filter(Boolean).join(' ')}
                    tabIndex={0}
                    role="button"
                    onClick={() => onSelect(item)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelect(item);
                      }
                    }}
                  >
                    {showRegion && (
                      <td className="quota-table__region">{item.location || '—'}</td>
                    )}
                    <td className="tag-rg-table__name">
                      <strong>{item.localized_name || item.name}</strong>
                      {item.localized_name && item.name && item.localized_name !== item.name && (
                        <span className="quota-table__sub">{item.name}</span>
                      )}
                    </td>
                    <td>
                      <span className={`quota-source-pill quota-source-pill--${item.source}`}>
                        {SOURCE_LABEL[item.source] || item.source}
                      </span>
                    </td>
                    <td className="quota-table__usage">
                      <UsageBar pct={item.usage_pct} status={item.status} />
                      <span>{item.usage_pct}%</span>
                    </td>
                    <td className="tag-rg-table__mono">{item.current?.toLocaleString() ?? '—'}</td>
                    <td className="tag-rg-table__mono">{item.limit?.toLocaleString() ?? '—'}</td>
                    <td>
                      <span className={`quota-status-pill quota-status-pill--${item.status}`}>
                        {item.status === 'ok' && <CheckCircle2 size={12} aria-hidden />}
                        {item.status !== 'ok' && <AlertTriangle size={12} aria-hidden />}
                        {STATUS_LABEL[item.status] || item.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function QuotaUsage() {
  const { subscription, subscriptionLabel } = useAdvancedSubscription();
  const [locations, setLocations] = useState([]);
  const [regionMode, setRegionMode] = usePersistedState('finops-quota-region-mode', 'single');
  const [location, setLocation] = usePersistedState('finops-quota-location', '');
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sourceFilter, setSourceFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (!subscription?.trim()) return;
    let cancelled = false;
    fetchQuotaLocations(subscription)
      .then((data) => {
        if (cancelled) return;
        const locs = data?.locations ?? [];
        setLocations(locs);
        if (!location && data?.default_location) {
          setLocation(data.default_location);
        }
      })
      .catch(() => {
        if (!cancelled) setLocations(['eastus', 'westus2', 'centralus']);
      });
    return () => { cancelled = true; };
  }, [subscription]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    if (regionMode === 'single' && !location) return;

    setLoading(true);
    setError(null);
    try {
      let data;
      if (regionMode === 'all') {
        const locs = locations.length ? locations : [location || 'eastus'];
        data = await fetchAllRegionsQuota(subscription, locs);
      } else {
        data = await fetchSubscriptionQuota(subscription, location);
        data = { ...data, mode: 'single', items: data.items || [] };
      }
      setPayload(data);
      setSelected(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription, regionMode, location, locations]);

  useEffect(() => {
    if (subscription && (regionMode === 'all' || location)) {
      load();
    }
  }, [subscription, regionMode, location, load]);

  useEffect(() => {
    setPayload(null);
    setSelected(null);
    setSourceFilter('');
    setStatusFilter('');
    setSearch('');
  }, [subscription]);

  const items = payload?.items ?? [];

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (sourceFilter && item.source !== sourceFilter) return false;
      if (statusFilter && item.status !== statusFilter) return false;
      if (!q) return true;
      const hay = [
        item.name,
        item.localized_name,
        item.source,
        item.location,
        SOURCE_LABEL[item.source],
      ].filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [items, sourceFilter, statusFilter, search]);

  const locationLabel = formatRegionLabel(
    regionMode === 'all' ? null : location,
    regionMode === 'all' ? 'all_regions' : 'single',
  );

  const selectedKey = selected ? `${selected.location || ''}:${selected.name}` : null;
  const hasFilters = !!(sourceFilter || statusFilter || search.trim());
  const isEmpty = !loading && !error && payload && items.length === 0;

  const toggleSource = useCallback((source) => {
    setSourceFilter((current) => (current === source ? '' : source));
    setSelected(null);
  }, []);

  return (
    <AdvancedToolLayout
      title="Quota usage"
      subtitle="Review subscription-level compute, network, and storage limits before you deploy or scale."
      iconKey="quotaUsage"
      iconRoute="/quota-usage"
      hasHeroBand
      metaItems={[
        locationLabel,
        payload?.items?.length != null && `${payload.items.length.toLocaleString()} quota types`,
        payload?.critical_count > 0 && `${payload.critical_count} critical`,
      ].filter(Boolean)}
      onRefresh={load}
      loading={loading}
      error={error}
      errorTitle="Could not load quota usage"
    >
      <QuotaUsageHero
        subscriptionLabel={subscriptionLabel}
        payload={payload}
        loading={loading}
        activeSource={sourceFilter}
        onSourceClick={toggleSource}
        locationLabel={locationLabel}
      />

      <QuotaDataNote mode={payload?.mode} locationLabel={locationLabel} />

      <section className="quota-region-bar card mb-4" aria-label="Region selection">
        <div className="quota-region-bar__head">
          <MapPin size={15} aria-hidden />
          <strong>Region</strong>
        </div>
        <div className="quota-region-bar__controls">
          <div className="quota-region-bar__modes" role="group" aria-label="Region scope">
            <button
              type="button"
              className={`quota-region-bar__mode${regionMode === 'single' ? ' quota-region-bar__mode--active' : ''}`}
              onClick={() => setRegionMode('single')}
              aria-pressed={regionMode === 'single'}
            >
              Single region
            </button>
            <button
              type="button"
              className={`quota-region-bar__mode${regionMode === 'all' ? ' quota-region-bar__mode--active' : ''}`}
              onClick={() => setRegionMode('all')}
              aria-pressed={regionMode === 'all'}
            >
              All deployed regions
            </button>
          </div>
          {regionMode === 'single' && (
            <select
              className="select-field quota-region-bar__select"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              aria-label="Azure region"
            >
              {!locations.length && <option value="">Loading regions…</option>}
              {locations.map((loc) => (
                <option key={loc} value={loc}>{formatRegionLabel(loc)}</option>
              ))}
            </select>
          )}
          {regionMode === 'all' && (
            <span className="quota-region-bar__hint">
              Scanning {locations.length.toLocaleString()} region{locations.length !== 1 ? 's' : ''} from inventory
            </span>
          )}
        </div>
      </section>

      {isEmpty ? (
        <AdvEmptyState
          title="No quota data for this region"
          description="Azure returned no usage limits for the selected region. Try another region or refresh."
          icon={Gauge}
        />
      ) : (
        <>
          <NearLimitStrip
            items={filteredItems}
            selectedId={selectedKey}
            onSelect={setSelected}
          />

          <FilterBar
            className="quota-filter-bar mb-4"
            search={{
              value: search,
              onChange: setSearch,
              placeholder: 'Search quota names…',
            }}
            selects={[
              {
                id: 'source',
                label: 'Category',
                value: sourceFilter,
                onChange: (v) => { setSourceFilter(v); setSelected(null); },
                options: SOURCE_OPTIONS,
              },
              {
                id: 'status',
                label: 'Status',
                value: statusFilter,
                onChange: (v) => { setStatusFilter(v); setSelected(null); },
                options: STATUS_OPTIONS,
              },
            ]}
            onClear={hasFilters ? () => { setSourceFilter(''); setStatusFilter(''); setSearch(''); setSelected(null); } : undefined}
            resultCount={{
              shown: filteredItems.length,
              total: items.length,
              label: 'quota types',
            }}
          />

          <QuotaTable
            items={filteredItems}
            loading={loading}
            selectedKey={selectedKey}
            onSelect={setSelected}
            showRegion={regionMode === 'all'}
          />
        </>
      )}
    </AdvancedToolLayout>
  );
}

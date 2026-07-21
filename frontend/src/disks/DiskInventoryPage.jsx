/**
 * Managed disks — exact port of design/concept-v2/#screen-disks
 */
import React, {
  useCallback, useContext, useMemo, useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { Download } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { AppCtx } from '../App';
import usePaginatedResources from '../hooks/usePaginatedResources';
import useFindingsIndex from '../hooks/useFindingsIndex';
import { fetchDashboardSyncStatus } from '../api/azure';
import { formatDate, formatDateTime } from '../utils/format';
import { encodeResourceRouteId } from '../utils/actionCentreV2Utils';
import {
  countResourcesWithFindings,
  sumResolvedSavingsForRows,
} from '../utils/resourceFindingsUtils';
import { apiRowsToConceptDisks } from './diskApiModel';
import {
  diskMatchesFilters,
  sortConceptDisks,
  formatDiskMetric,
  formatDiskCad,
  diskTableColumns,
  severityLabel,
} from './diskList';
import { LoadingState, SubscriptionRequired, QueryErrorState } from '../components/QueryStates';

function DiskSortableHeader({
  colKey, label, sortKey, sortDir, onSort,
}) {
  const active = sortKey === colKey;
  return (
    <th
      className={[
        'disk-sortable',
        active ? 'active' : '',
        active && sortDir === 'asc' ? 'asc' : '',
        active && sortDir === 'desc' ? 'desc' : '',
      ].filter(Boolean).join(' ')}
      scope="col"
      data-disk-sort={colKey}
      onClick={() => onSort(colKey)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSort(colKey);
        }
      }}
      tabIndex={0}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      {label}
    </th>
  );
}

function DiskInventoryRow({ disk, currency, onOpen }) {
  const p = disk.properties || {};
  const m = disk.metrics || {};
  const cost = disk.cost || {};
  const finding = disk.finding;
  const stateClass = p.diskState === 'Unattached' ? 'disk-state--warn' : 'disk-state--ok';
  const attachVal = p.managedBy === '—' || !p.managedBy
    ? <span className="muted">Unattached</span>
    : p.managedBy;

  return (
    <tr
      className="disk-row--clickable"
      data-disk-id={disk.id}
      tabIndex={0}
      onClick={() => onOpen(disk)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(disk);
        }
      }}
    >
      <td>
        <div className="resource-cell">
          <div className="resource-icon resource-icon--disk">DSK</div>
          <div className="resource-cell__body">
            <strong>{disk.name}</strong>
            <small>{disk.resourceGroup}</small>
          </div>
        </div>
      </td>
      <td>{p.diskSizeGB != null ? `${p.diskSizeGB} GB` : '—'}</td>
      <td><code className="disk-sku">{p.sku || '—'}</code></td>
      <td>{p.tier || '—'}</td>
      <td><span className={`disk-state ${stateClass}`}>{p.diskState || '—'}</span></td>
      <td>{attachVal}</td>
      <td>{p.provisioningState || '—'}</td>
      <td className="disk-metric">{formatDiskMetric(m.disk_iops_utilization_pct, '%')}</td>
      <td className="disk-metric">{formatDiskMetric(m.disk_throughput_utilization_pct, '%')}</td>
      <td className="cost-cell">{formatDiskCad(cost.billed_mtd, currency)}</td>
      <td className="cost-cell cost-cell--muted">{formatDiskCad(cost.retail_monthly, currency)}</td>
      <td>
        <div className="disk-finding-cell">
          {finding ? (
            <>
              <span className={`sev sev-${finding.severity}`}>{severityLabel(finding.severity)}</span>
              {finding.findingCount > 1 ? (
                <span className="disk-finding-count-badge">
                  {finding.findingCount}
                </span>
              ) : null}
            </>
          ) : (
            <span className="disk-no-finding">—</span>
          )}
          {finding && finding.savings > 0 ? (
            <span className="disk-savings">{formatDiskCad(finding.savings, currency)}/mo</span>
          ) : null}
        </div>
      </td>
      <td className="disk-location">{disk.region || '—'}</td>
    </tr>
  );
}

export default function DiskInventoryPage() {
  const { subscription, billingCurrency, subscriptionOptions } = useContext(AppCtx);
  const navigate = useNavigate();
  const currency = billingCurrency || 'CAD';
  const subLabel = subscriptionOptions.find((s) => s.subscriptionId === subscription)?.displayName;

  const [search, setSearch] = useState('');
  const [chip, setChip] = useState('all');
  const [sortKey, setSortKey] = useState('name');
  const [sortDir, setSortDir] = useState('asc');

  const { items: data, isLoading, isError, error, refetch, isFetching } = usePaginatedResources({
    apiPath: '/resources/disks',
    subscription,
    enabled: !!subscription,
    includeMetrics: true,
    includeCosts: true,
  });

  const { byResourceId, indexReady } = useFindingsIndex(subscription);

  const { data: syncStatus } = useQuery({
    queryKey: ['dashboard-sync', subscription],
    queryFn: () => fetchDashboardSyncStatus({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 120_000,
  });

  const conceptDisks = useMemo(
    () => apiRowsToConceptDisks(data, byResourceId, { indexReady, apiPath: '/resources/disks' }),
    [data, byResourceId, indexReady],
  );

  const sorted = useMemo(() => {
    const filtered = conceptDisks.filter((d) => diskMatchesFilters(d, { search, chip }));
    return sortConceptDisks(filtered, sortKey, sortDir);
  }, [conceptDisks, search, chip, sortKey, sortDir]);

  const findingsCount = useMemo(
    () => countResourcesWithFindings(data, byResourceId, { indexReady }),
    [data, byResourceId, indexReady],
  );

  const savingsTotal = useMemo(
    () => sumResolvedSavingsForRows(data, byResourceId, { indexReady }),
    [data, byResourceId, indexReady],
  );

  const hasFilter = Boolean(search) || chip !== 'all';
  const columns = diskTableColumns();

  const handleSort = useCallback((colKey) => {
    if (sortKey === colKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(colKey);
    setSortDir(colKey === 'name' || colKey === 'region' ? 'asc' : 'desc');
  }, [sortKey]);

  const clearFilters = useCallback(() => {
    setSearch('');
    setChip('all');
  }, []);

  const openDisk = useCallback((disk) => {
    const id = disk?.id || disk?._raw?.id;
    if (id) navigate(`/resource/${encodeResourceRouteId(id)}`);
  }, [navigate]);

  const analysisLabel = useMemo(() => {
    const at = syncStatus?.analysis?.last_run_at || syncStatus?.last_analysis_at;
    return at ? `Analysis ${formatDateTime(at)}` : `Analysis ${formatDate(new Date())}`;
  }, [syncStatus]);

  if (!subscription) return <SubscriptionRequired />;
  if (isLoading) return <LoadingState message="Loading managed disks…" />;
  if (isError) return <QueryErrorState error={error} onRetry={refetch} />;

  return (
    <section id="screen-disks" className="screen disk-v2" aria-label="Managed disks">
      <header className="page-head page-head--disks">
        <div>
          <h1>Managed disks</h1>
          <div className="page-meta">
            <span className="meta-pill meta-pill--ok">
              <span className="meta-pill__dot" />
              {analysisLabel}
            </span>
            <span className="meta-pill">
              Assessment v2 · <code className="inline-code">data/disk-assessment.json</code>
            </span>
            {subLabel ? <span className="meta-pill">{subLabel}</span> : null}
          </div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-ghost btn-icon" id="disk-export-btn" aria-label="Export disk inventory">
            <Download size={18} aria-hidden />
            Export
          </button>
          {isFetching ? <span className="meta-pill">Refreshing…</span> : null}
        </div>
      </header>

      <p className="disk-intel-strip" id="disk-intel-strip" aria-live="polite">
        <span><strong>{conceptDisks.length}</strong> disks</span>
        <span className="disk-intel-strip__dot" aria-hidden="true">·</span>
        <span><strong>{findingsCount}</strong> with findings</span>
        <span className="disk-intel-strip__dot" aria-hidden="true">·</span>
        <span className="disk-intel-strip__seg--savings">
          <strong>{formatDiskCad(savingsTotal, currency).replace('.00', '')}</strong> potential savings/mo
        </span>
      </p>

      <div className="disk-command" id="disk-command">
        <div className="disk-command__row">
          <div className="search-wrap disk-command__search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input
              type="search"
              className="search"
              id="disk-search"
              placeholder="Search disks"
              aria-label="Search disks"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="disk-command__clear link link--sm"
            id="disk-clear-filters"
            hidden={!hasFilter}
            onClick={clearFilters}
          >
            Clear filters
          </button>
        </div>
        <div className="disk-chip-bar" role="toolbar" aria-label="Filter disks">
          {[
            { id: 'all', label: 'All disks' },
            { id: 'finding', label: 'With findings' },
            { id: 'unattached', label: 'Unattached' },
            { id: 'attached', label: 'Attached' },
            { id: 'premium', label: 'Premium tier', premium: true },
          ].map((item) => (
            <button
              key={item.id}
              type="button"
              className={['disk-chip', item.premium ? 'disk-chip--premium' : '', chip === item.id ? 'active' : ''].filter(Boolean).join(' ')}
              data-disk-chip={item.id}
              onClick={() => setChip(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <p className="disk-filter-note" id="disk-filter-note" aria-live="polite">
          {hasFilter
            ? `Showing ${sorted.length} of ${conceptDisks.length} disks`
            : `Showing ${sorted.length} disks · identity → config → metrics → cost → findings → location`}
        </p>
      </div>

      <div className="panel table-panel disk-table-panel" id="disk-table-panel">
        <div className="disk-table-head">
          <h2 className="section-title section-title--bar">Disk inventory</h2>
          <span className="disk-table-head__count" id="disk-count">{sorted.length}</span>
        </div>
        <div className="disk-table-scroll">
          <table className="disk-inventory-table" id="disk-inventory-table">
            <thead>
              <tr id="disk-table-head-row">
                {columns.map((col) => (
                  <DiskSortableHeader
                    key={col.key}
                    colKey={col.key}
                    label={col.label}
                    sortKey={sortKey}
                    sortDir={sortDir}
                    onSort={handleSort}
                  />
                ))}
              </tr>
            </thead>
            <tbody id="disk-inventory-tbody">
              {sorted.map((disk) => (
                <DiskInventoryRow key={disk.id} disk={disk} currency={currency} onOpen={openDisk} />
              ))}
            </tbody>
          </table>
        </div>
        {sorted.length === 0 ? (
          <p className="disk-empty" id="disk-empty">
            No disks match your filters.{' '}
            <button type="button" className="link link--sm" id="disk-empty-clear" onClick={clearFilters}>
              Clear filters
            </button>
          </p>
        ) : null}
      </div>
    </section>
  );
}

import React, { useContext, useMemo, useRef, useState, Suspense, lazy } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import useQueryWithTimeout from '../hooks/useQueryWithTimeout';
import {
  bulkUpdateFindingStatus,
  fetchFindings,
  fetchFindingsSummary,
  updateFindingStatus,
} from '../api/azure';
import { getErrorMessage } from '../api/errors';
import PageHeader from '../components/PageHeader';
import FilterBar from '../components/FilterBar';
import RecommendationFilterTabs, { buildRecommendationFilterSelects } from '../components/RecommendationFilterTabs';
import RecommendationsHero from '../components/recommendations/RecommendationsHero';
import RecommendationsSeverityView from '../components/recommendations/RecommendationsSeverityView';
import RecommendationDetailCard, {
  ResourceRecommendationGroup,
} from '../components/RecommendationDetailCard';
import BulkActionBar from '../components/BulkActionBar';
import PrintExportButton from '../components/PrintExportButton';
import FilterPresetsBar from '../components/filtering/FilterPresetsBar';
import VirtualizedTable from '../components/table/VirtualizedTable';
import useFilterPresets from '../hooks/useFilterPresets';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import { List, Download, AlertTriangle, CircleDot } from 'lucide-react';
import { PAGE_ICONS } from '../config/assetIcons';
import { matchFinding, isCostOptimizationFinding } from '../utils/filterUtils';
import { dedupeOpenFindings, normalizeArmId } from '../utils/findingDedupe';
import {
  groupFindingsByResourceGroup,
  groupFindingsByResourceType,
} from '../utils/optimizationGrouping';
import OptimizationGroupByToggle from '../components/optimization/OptimizationGroupByToggle';
import FindingsGroupedView from '../components/optimization/FindingsGroupedView';
import useOptimizationGroupBy from '../hooks/useOptimizationGroupBy';

const RecommendationsBubbleChart = lazy(() => import('../components/recommendations/RecommendationsBubbleChart'));

const FINDINGS_LIMIT = 2000;
const LIST_VIRTUAL_THRESHOLD = 60;
const UNDO_MS = 5000;

function matchesTypeFilter(finding, typeFilter) {
  if (!typeFilter) return true;
  if (typeFilter === 'cost') return isCostOptimizationFinding(finding);
  if (typeFilter === 'governance') return !isCostOptimizationFinding(finding);
  return true;
}

function groupByResource(findings) {
  const map = new Map();
  for (const f of findings) {
    const key = normalizeArmId(f.resource_id) || '__unknown__';
    if (!map.has(key)) {
      map.set(key, {
        resource_id: f.resource_id,
        resource_name: f.resource_name,
        resource_group: f.resource_group,
        location: f.location,
        resource_type: f.resource_type,
        resource_app_href: f.resource_app_href,
        azure_portal_url: f.azure_portal_url,
        findings: [],
        totalSavings: 0,
      });
    }
    const group = map.get(key);
    group.findings.push(f);
    group.totalSavings += f.estimated_savings_usd || 0;
  }
  return [...map.values()].sort((a, b) => {
    if (b.totalSavings !== a.totalSavings) return b.totalSavings - a.totalSavings;
    return b.findings.length - a.findings.length;
  });
}

function downloadFindingsCsv(findings, currency) {
  const headers = ['Rule', 'Severity', 'Category', 'Status', 'Resource', 'Resource group', 'Est. savings/mo', 'Recommendation'];
  const escape = (v) => {
    const s = String(v ?? '').replace(/"/g, '""');
    return `"${s}"`;
  };
  const rows = findings.map((f) => [
    f.rule_name,
    f.severity,
    f.category,
    f.status,
    f.resource_name,
    f.resource_group,
    f.estimated_savings_usd ?? '',
    f.recommendation,
  ].map(escape).join(','));
  const blob = new Blob([[headers.join(','), ...rows].join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `recommendations-${currency.toLowerCase()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function Recommendations({ embedded = false }) {
  const { subscription, billingCurrency, subscriptionOptions } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const { showUndoToast } = useToast();
  const currency = billingCurrency || 'CAD';
  const qc = useQueryClient();
  const subLabel = subscriptionOptions.find((s) => s.subscriptionId === subscription)?.displayName;
  const pendingStatusRef = useRef(new Map());

  const [sevFilter, setSevFilter] = useState('');
  const [catFilter, setCatFilter] = useState('');
  const [statusFilter, setStatus] = useState('open');
  const [typeFilter, setTypeFilter] = useState('');
  const [search, setSearch] = useState('');
  const [viewMode, setViewMode] = useState('severity');
  const [groupBy, setGroupBy] = useOptimizationGroupBy('resource_type');
  const [actionError, setActionError] = useState('');
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [presetModalOpen, setPresetModalOpen] = useState(false);
  const [presetName, setPresetName] = useState('');

  const currentFilters = useMemo(() => ({
    search,
    sevFilter,
    catFilter,
    statusFilter,
    typeFilter,
  }), [search, sevFilter, catFilter, statusFilter, typeFilter]);

  const { presets, savePreset, deletePreset } = useFilterPresets(
    `recommendations:${subscription || 'none'}`,
    currentFilters,
  );

  const {
    data: findings = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['findings', subscription, sevFilter, catFilter, statusFilter, FINDINGS_LIMIT],
    queryFn: () => fetchFindings({
      subscription_id: subscription,
      severity: sevFilter || undefined,
      category: catFilter || undefined,
      status: statusFilter || undefined,
      limit: FINDINGS_LIMIT,
    }),
    enabled: !!subscription,
  });

  const { data: summary, isLoading: summaryLoading } = useQueryWithTimeout({
    queryKey: ['findings-summary', subscription],
    queryFn: () => fetchFindingsSummary({ subscription_id: subscription }),
    enabled: !!subscription,
    timeout: 3000,
    allowEmpty: true,
  });

  const invalidateFindingQueries = () => {
    qc.invalidateQueries({ queryKey: ['findings'] });
    qc.invalidateQueries({ queryKey: ['findings-summary'] });
    qc.invalidateQueries({ queryKey: ['findings-index'] });
    qc.invalidateQueries({ queryKey: ['finding-activity'] });
    qc.invalidateQueries({
      predicate: (q) => Array.isArray(q.queryKey)
        && typeof q.queryKey[0] === 'string'
        && q.queryKey[0].startsWith('/resources'),
    });
  };

  const mut = useMutation({
    mutationFn: ({ id, status }) => updateFindingStatus(id, status, subscription),
    onMutate: () => setActionError(''),
    onSuccess: () => invalidateFindingQueries(),
    onError: (err) => setActionError(getErrorMessage(err, 'Could not update recommendation status.')),
  });

  const bulkMut = useMutation({
    mutationFn: ({ ids, status }) => bulkUpdateFindingStatus(ids, status, subscription),
    onMutate: () => setActionError(''),
    onSuccess: () => {
      setSelectedIds(new Set());
      invalidateFindingQueries();
    },
    onError: (err) => setActionError(getErrorMessage(err, 'Could not update selected recommendations.')),
  });

  const statusLabel = (status) => {
    if (status === 'implemented') return 'implemented';
    if (status === 'ignored') return 'dismissed';
    return status;
  };

  const commitStatusChange = (id, status) => {
    mut.mutate({ id, status });
  };

  const handleStatusChange = ({ id, status, label }) => {
    const existing = pendingStatusRef.current.get(id);
    if (existing?.timer) window.clearTimeout(existing.timer);

    const timer = window.setTimeout(() => {
      pendingStatusRef.current.delete(id);
      commitStatusChange(id, status);
    }, UNDO_MS);

    pendingStatusRef.current.set(id, { timer, status });

    showUndoToast(
      `Marked '${label}' as ${statusLabel(status)}`,
      () => {
        const pending = pendingStatusRef.current.get(id);
        if (pending?.timer) window.clearTimeout(pending.timer);
        pendingStatusRef.current.delete(id);
      },
      { duration: UNDO_MS },
    );
  };

  const handleBulkStatus = (status) => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    bulkMut.mutate({ ids, status });
  };

  const toggleSelected = (id, checked) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const displayFindings = useMemo(
    () => (statusFilter === 'open' || !statusFilter ? dedupeOpenFindings(findings) : findings),
    [findings, statusFilter],
  );

  const filtered = useMemo(
    () => displayFindings.filter((f) => matchFinding(f, search) && matchesTypeFilter(f, typeFilter)),
    [displayFindings, search, typeFilter],
  );

  const selectableFindings = useMemo(
    () => filtered.filter((f) => f.status === 'open'),
    [filtered],
  );

  const grouped = useMemo(() => groupByResource(filtered), [filtered]);
  const groupedByType = useMemo(() => groupFindingsByResourceType(filtered), [filtered]);
  const groupedByRg = useMemo(() => groupFindingsByResourceGroup(filtered), [filtered]);

  const totalSavings = filtered.reduce((s, f) => s + (f.estimated_savings_usd || 0), 0);
  const truncated = findings.length >= FINDINGS_LIMIT;
  const hasFilters = !!(
    search
    || sevFilter
    || catFilter
    || typeFilter
    || (statusFilter && statusFilter !== 'open')
  );

  const hasSecondaryFilters = !!(search || typeFilter);

  const tabStatusCounts = useMemo(() => {
    if (!hasSecondaryFilters || !summary?.by_status) return null;
    const counts = { ...summary.by_status };
    const tabKey = statusFilter || 'open';
    if (tabKey === '') {
      counts.open = filtered.length;
    } else {
      counts[tabKey] = filtered.length;
    }
    return counts;
  }, [hasSecondaryFilters, summary, statusFilter, filtered.length]);

  const clearFilters = () => {
    setSearch('');
    setSevFilter('');
    setCatFilter('');
    setTypeFilter('');
    setStatus('open');
  };

  const applyPreset = (preset) => {
    const f = preset.filters || {};
    setSearch(f.search || '');
    setSevFilter(f.sevFilter || '');
    setCatFilter(f.catFilter || '');
    setTypeFilter(f.typeFilter || '');
    setStatus(f.statusFilter || 'open');
  };

  const handleSavePreset = () => {
    setPresetName('');
    setPresetModalOpen(true);
  };

  const commitSavePreset = () => {
    const name = presetName.trim();
    if (!name) return;
    savePreset(name);
    setPresetModalOpen(false);
    setPresetName('');
  };

  const toggleSelectAll = (checked) => {
    if (checked) {
      setSelectedIds(new Set(selectableFindings.map((f) => f.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const allVisibleSelected = selectableFindings.length > 0
    && selectableFindings.every((f) => selectedIds.has(f.id));

  const filterSelects = buildRecommendationFilterSelects({
    summary,
    sevFilter,
    onSevChange: setSevFilter,
    catFilter,
    onCatChange: setCatFilter,
    typeFilter,
    onTypeChange: setTypeFilter,
  });

  const viewToggle = (
    <div className="rec-view-toolbar no-print">
      <OptimizationGroupByToggle value={groupBy} onChange={setGroupBy} />
      {groupBy === 'flat' && (
      <div className="rec-view-toggle" role="group" aria-label="View mode">
      <button
        type="button"
        className={`btn btn-ghost btn-sm${viewMode === 'severity' ? ' active' : ''}`}
        onClick={() => setViewMode('severity')}
      >
        <AlertTriangle size={13} /> By severity
      </button>
      <button
        type="button"
        className={`btn btn-ghost btn-sm${viewMode === 'chart' ? ' active' : ''}`}
        onClick={() => setViewMode('chart')}
      >
        <CircleDot size={13} /> Chart
      </button>
      <button
        type="button"
        className={`btn btn-ghost btn-sm${viewMode === 'list' ? ' active' : ''}`}
        onClick={() => setViewMode('list')}
      >
        <List size={13} /> All details
      </button>
      </div>
      )}
      <div className="rec-view-toggle rec-view-toggle--actions">
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => downloadFindingsCsv(filtered, currency)}
        disabled={filtered.length === 0}
      >
        <Download size={13} /> Export
      </button>
      <PrintExportButton />
      </div>
    </div>
  );

  return (
    <div className={`page-shell recommendations-page${embedded ? ' optimization-hub-panel__content recommendations-page--embedded' : ''}`}>
      {!embedded && (
      <PageHeader
        title="Recommendations"
        iconKey={PAGE_ICONS.recommendations}
      />
      )}

      {actionError && (
        <div className="alert alert--danger" role="alert">
          {actionError}
        </div>
      )}

      {!subscription && <SubscriptionRequired />}

      {subscription && (
        <div className="recommendations-layout">
          <RecommendationsHero
            subscriptionLabel={subLabel}
            summary={summary}
            filteredCount={filtered.length}
            filteredSavings={totalSavings}
            currency={currency}
            isLoading={summaryLoading && !summary}
          />

          {subscription && (
            <div className="no-print">
              {viewToggle}
            </div>
          )}

          <section className="rec-filter-panel card">
            <RecommendationFilterTabs
              summary={summary}
              statusCounts={tabStatusCounts}
              statusFilter={statusFilter}
              onStatusChange={setStatus}
            />
            {hasSecondaryFilters && (
              <p className="rec-filter-hint" role="status">
                Tab counts reflect your search and type filters for the active status.
              </p>
            )}
            <FilterPresetsBar
              presets={presets}
              onApply={applyPreset}
              onSave={handleSavePreset}
              onDelete={deletePreset}
            />
            <FilterBar
              className="filter-bar--compact rec-filter-bar"
              search={{
                value: search,
                onChange: setSearch,
                placeholder: 'Search resource, rule, or recommendation…',
              }}
              selects={filterSelects}
              onClear={hasFilters ? clearFilters : undefined}
              resultCount={{
                shown: filtered.length,
                total: findings.length !== filtered.length ? findings.length : undefined,
                label: 'recommendations',
              }}
            />
          </section>

          <BulkActionBar
            count={selectedIds.size}
            onResolve={() => handleBulkStatus('resolved')}
            onDismiss={() => handleBulkStatus('ignored')}
            onExport={() => downloadFindingsCsv(
              filtered.filter((f) => selectedIds.has(f.id)),
              currency,
            )}
            onClear={() => setSelectedIds(new Set())}
            resolveDisabled={!isAdmin}
            dismissDisabled={bulkMut.isPending}
          />

          {truncated && (
            <div className="rec-truncation-banner" role="status">
              Showing the first {FINDINGS_LIMIT.toLocaleString()} recommendations. Narrow filters to see more.
            </div>
          )}

          {isLoading && <LoadingState message="Loading recommendations…" />}
          {isError && <QueryErrorState error={error} onRetry={refetch} />}

          {!isLoading && !isError && filtered.length === 0 && (
            <EmptyState
              iconKey={PAGE_ICONS.recommendations}
              message={hasFilters
                ? 'No recommendations match your filters.'
                : (isAdmin
                  ? 'No recommendations yet. Run sync and analysis from Sync center.'
                  : 'No recommendations yet.')}
            >
              {hasFilters ? (
                <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
                  Clear filters
                </button>
              ) : (
                <Link to="/" className="btn btn-secondary btn-sm">Go to dashboard</Link>
              )}
            </EmptyState>
          )}

          {!isLoading && !isError && filtered.length > 0 && groupBy === 'resource_type' && (
            <FindingsGroupedView
              groups={groupedByType}
              currency={currency}
              subscriptionId={subscription}
              onStatusChange={handleStatusChange}
              statusPending={mut.isPending || bulkMut.isPending}
              allowResolve={isAdmin}
              showStatus={!statusFilter || statusFilter === ''}
              selectableFindings={selectableFindings}
              selectedIds={selectedIds}
              onSelectChange={toggleSelected}
            />
          )}

          {!isLoading && !isError && filtered.length > 0 && groupBy === 'resource_group' && (
            <FindingsGroupedView
              groups={groupedByRg}
              currency={currency}
              subscriptionId={subscription}
              onStatusChange={handleStatusChange}
              statusPending={mut.isPending || bulkMut.isPending}
              allowResolve={isAdmin}
              showStatus={!statusFilter || statusFilter === ''}
              selectableFindings={selectableFindings}
              selectedIds={selectedIds}
              onSelectChange={toggleSelected}
            />
          )}

          {!isLoading && !isError && filtered.length > 0 && groupBy === 'flat' && viewMode === 'chart' && (
            <Suspense fallback={<div className="chart-slot chart-slot--tall chart-slot--loading" aria-busy="true" aria-label="Loading chart" />}>
              <RecommendationsBubbleChart
                findings={filtered}
                currency={currency}
                onSelect={(finding) => {
                  if (finding?.id) {
                    setViewMode('list');
                    setSelectedIds(new Set([finding.id]));
                  }
                }}
              />
            </Suspense>
          )}

          {!isLoading && !isError && filtered.length > 0 && groupBy === 'flat' && viewMode === 'severity' && (
            <RecommendationsSeverityView
              findings={filtered}
              currency={currency}
              subscriptionId={subscription}
              onStatusChange={handleStatusChange}
              statusPending={mut.isPending || bulkMut.isPending}
              allowResolve={isAdmin}
              showStatus={!statusFilter || statusFilter === ''}
              selectableFindings={selectableFindings}
              selectedIds={selectedIds}
              onSelectChange={toggleSelected}
              allVisibleSelected={allVisibleSelected}
              onSelectAll={toggleSelectAll}
            />
          )}

          {!isLoading && !isError && filtered.length > 0 && groupBy === 'resource' && (
            <div className="rec-groups">
              {grouped.map((group) => (
                <ResourceRecommendationGroup
                  key={group.resource_id || group.resource_name}
                  group={group}
                  currency={currency}
                  subscriptionId={subscription}
                  onStatusChange={handleStatusChange}
                  statusPending={mut.isPending}
                  allowResolve={isAdmin}
                  showStatus={!statusFilter || statusFilter === ''}
                />
              ))}
            </div>
          )}

          {!isLoading && !isError && filtered.length > 0 && groupBy === 'flat' && viewMode === 'list' && (
            <div className="rec-flat-list">
              {selectableFindings.length > 0 && (
                <label className="rec-select-all">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={(e) => toggleSelectAll(e.target.checked)}
                  />
                  <span>Select all visible open recommendations</span>
                </label>
              )}
              {filtered.length >= LIST_VIRTUAL_THRESHOLD ? (
                <VirtualizedTable
                  className="virtual-table--recommendations"
                  items={filtered}
                  rowHeight={148}
                  height={640}
                >
                  {(finding) => (
                    <RecommendationDetailCard
                      key={finding.id}
                      finding={finding}
                      currency={currency}
                      subscriptionId={subscription}
                      onStatusChange={handleStatusChange}
                      statusPending={mut.isPending || bulkMut.isPending}
                      allowResolve={isAdmin}
                      defaultExpanded={false}
                      showStatus={!statusFilter || statusFilter === ''}
                      selectable={finding.status === 'open'}
                      selected={selectedIds.has(finding.id)}
                      onSelectChange={toggleSelected}
                    />
                  )}
                </VirtualizedTable>
              ) : (
                filtered.map((f) => (
                  <RecommendationDetailCard
                    key={f.id}
                    finding={f}
                    currency={currency}
                    subscriptionId={subscription}
                    onStatusChange={handleStatusChange}
                    statusPending={mut.isPending || bulkMut.isPending}
                    allowResolve={isAdmin}
                    defaultExpanded={false}
                    showStatus={!statusFilter || statusFilter === ''}
                    selectable={f.status === 'open'}
                    selected={selectedIds.has(f.id)}
                    onSelectChange={toggleSelected}
                  />
                ))
              )}
            </div>
          )}
        </div>
      )}

      {presetModalOpen && (
        <div className="modal-overlay" role="presentation" onClick={() => setPresetModalOpen(false)}>
          <div
            className="modal card preset-save-modal"
            role="dialog"
            aria-labelledby="preset-save-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="preset-save-title" className="preset-save-modal__title">Save filter preset</h3>
            <label className="preset-save-modal__field">
              <span>Name</span>
              <input
                type="text"
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
                placeholder="e.g. High severity compute"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitSavePreset();
                }}
              />
            </label>
            <div className="preset-save-modal__actions">
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPresetModalOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={commitSavePreset}
                disabled={!presetName.trim()}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

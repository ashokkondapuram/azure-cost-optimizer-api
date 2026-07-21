import React, { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { AppCtx } from '../App';
import useFindingsIndex from '../hooks/useFindingsIndex';
import useOptimizationActions from '../hooks/useOptimizationActions';
import usePaginatedResources from '../hooks/usePaginatedResources';
import { fetchDashboardSyncStatus } from '../api/azure';
import { useQuery } from '@tanstack/react-query';
import { normalizeArmId } from '../utils/findingDedupe';
import { INVENTORY_API_PATH, resourceRowId } from '../utils/resourceRowId';
import { resolveSubscriptionLabel } from '../utils/subscriptionDisplay';
import { ACTION_INDEX_LIMIT } from '../utils/actionUtils';
import {
  DEFAULT_AC_FILTERS,
  DEFAULT_AC_SORT,
  acHasActiveFilters,
  buildFindingTableRows,
  computeIntelStrip,
  encodeResourceRouteId,
  filterFindingRows,
  loadAcFiltersState,
  parseAcFiltersFromSearchParams,
  resolveActionCentreEmptyState,
  saveAcFiltersState,
  sortFindingRows,
} from '../utils/actionCentreV2Utils';
import ActionCentrePageHead from '../components/action-centre/ActionCentrePageHead';
import ActionCentreIntelStrip from '../components/action-centre/ActionCentreIntelStrip';
import ActionCentreCommandBar from '../components/action-centre/ActionCentreCommandBar';
import ActionCentreFindingsTable from '../components/action-centre/ActionCentreFindingsTable';
import { SubscriptionRequired, QueryErrorState, LoadingState } from '../components/QueryStates';

export default function ActionCentre() {
  const { subscription, subscriptionOptions, billingCurrency } = useContext(AppCtx);
  const [searchParams] = useSearchParams();
  const currency = billingCurrency || 'CAD';
  const resourceRedirect = searchParams.get('resource') || searchParams.get('resourceId');
  const subscriptionLabel = resolveSubscriptionLabel(subscription, subscriptionOptions);

  const saved = loadAcFiltersState();
  const [filters, setFilters] = useState(() => {
    const fromUrl = parseAcFiltersFromSearchParams(searchParams);
    return saved?.filters ? { ...fromUrl, ...saved.filters } : fromUrl;
  });
  const [sort, setSort] = useState(saved?.sort || DEFAULT_AC_SORT);

  useEffect(() => {
    saveAcFiltersState(filters, sort);
  }, [filters, sort]);

  const {
    findings,
    summary,
    findingsTotal,
    truncated,
    isLoading: findingsLoading,
    isError: findingsError,
    refreshFailed: findingsRefreshFailed,
    error: findingsErrorDetail,
    refetch: refetchFindings,
  } = useFindingsIndex(subscription, { inventoryOnly: false });

  const {
    items: resources,
    isLoading: resourcesLoading,
    isError: resourcesError,
    error: resourcesErrorDetail,
    refetch: refetchResources,
  } = usePaginatedResources({
    apiPath: INVENTORY_API_PATH,
    subscription,
    enabled: !!subscription,
    inventoryOnly: true,
  });

  const {
    items: actions,
    summary: actionsSummary,
    isError: actionsError,
    error: actionsErrorDetail,
    refetch: refetchActions,
  } = useOptimizationActions(
    subscription,
    { inventory_only: false },
    { limit: ACTION_INDEX_LIMIT, infinite: false },
  );

  const { data: syncStatus } = useQuery({
    queryKey: ['dashboard-sync', subscription],
    queryFn: () => fetchDashboardSyncStatus({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 120_000,
  });

  const resourceById = useMemo(() => {
    const map = new Map();
    for (const row of resources || []) {
      const key = normalizeArmId(resourceRowId(row));
      if (key) map.set(key, row);
    }
    return map;
  }, [resources]);

  const actionsByResource = useMemo(() => {
    const map = new Map();
    for (const action of actions || []) {
      const key = normalizeArmId(action.resource_id);
      if (!key) continue;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(action);
    }
    return map;
  }, [actions]);

  const allRows = useMemo(
    () => buildFindingTableRows({
      findings,
      resourceById,
      actionsByResource,
      currency,
      subscriptionLabel,
    }),
    [findings, resourceById, actionsByResource, currency, subscriptionLabel],
  );

  const visibleRows = useMemo(
    () => sortFindingRows(filterFindingRows(allRows, filters), sort),
    [allRows, filters, sort],
  );

  const hasActiveFilters = acHasActiveFilters(filters);

  const intel = useMemo(
    () => computeIntelStrip({
      summary: { ...summary, ...actionsSummary },
      visibleRows,
      hasActiveFilters,
      currency,
    }),
    [summary, actionsSummary, visibleRows, hasActiveFilters, currency],
  );

  const showInitialSkeleton = findingsLoading && !findings.length && !summary;
  const resourcesRefreshFailed = resourcesError && resources.length > 0;

  const analysisAt = syncStatus?.analysis?.last_job_at || syncStatus?.last_analysis_at || null;

  const emptyState = resolveActionCentreEmptyState({
    totalCount: findingsTotal || allRows.length,
    hasActiveFilters,
    analysisAt,
    syncStatus,
  });

  const handleFilter = useCallback((group, value) => {
    setFilters((prev) => ({ ...prev, [group]: value }));
  }, []);

  const handleSearch = useCallback((value) => {
    setFilters((prev) => ({ ...prev, search: value }));
  }, []);

  const handleClear = useCallback(() => {
    setFilters({ ...DEFAULT_AC_FILTERS });
    setSort(DEFAULT_AC_SORT);
  }, []);

  const handleSort = useCallback((col) => {
    setSort((prev) => {
      const [currentCol, currentDir] = prev.split('-');
      if (currentCol === col) {
        return `${col}-${currentDir === 'desc' ? 'asc' : 'desc'}`;
      }
      const defaultDir = ['resource', 'recommendation', 'category', 'source', 'status'].includes(col)
        ? 'asc'
        : 'desc';
      return `${col}-${defaultDir}`;
    });
  }, []);

  const handleExport = useCallback(() => {
    const header = ['Resource', 'Recommendation', 'Category', 'Monthly cost', 'Savings', 'Severity', 'Source', 'Status'];
    const lines = visibleRows.map((r) => [
      r.resource,
      r.recommendation,
      r.categoryLabel,
      r.cost,
      r.savings,
      r.severity,
      r.source,
      r.workflow,
    ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','));
    const csv = [header.join(','), ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'action-centre-findings.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, [visibleRows]);

  const refetchAll = () => {
    refetchFindings();
    refetchResources();
    refetchActions();
  };

  if (resourceRedirect) {
    return <Navigate to={`/resource/${encodeResourceRouteId(resourceRedirect)}`} replace />;
  }

  if (!subscription) {
    return (
      <section className="action-centre-v2" aria-label="Action centre">
        <SubscriptionRequired />
      </section>
    );
  }

  if (findingsError) {
    return (
      <section className="action-centre-v2" aria-label="Action centre">
        <ActionCentrePageHead analysisAt={analysisAt} onExport={handleExport} />
        <QueryErrorState
          error={findingsErrorDetail}
          onRetry={refetchAll}
          title="Could not load action centre"
        />
      </section>
    );
  }

  if (showInitialSkeleton) {
    return (
      <section className="action-centre-v2" aria-label="Action centre">
        <LoadingState message="Loading action centre…" />
      </section>
    );
  }

  return (
    <section className="action-centre-v2" aria-label="Action centre">
      <ActionCentrePageHead analysisAt={analysisAt} onExport={handleExport} />

      {findingsRefreshFailed && (
        <div className="panel" role="alert" style={{ marginBottom: 16 }}>
          <QueryErrorState
            error={findingsErrorDetail}
            onRetry={refetchFindings}
            title="Some findings could not be refreshed"
          />
        </div>
      )}

      {resourcesRefreshFailed && (
        <div className="panel" role="alert" style={{ marginBottom: 16 }}>
          <QueryErrorState
            error={resourcesErrorDetail}
            onRetry={refetchResources}
            title="Resource details could not be refreshed"
          />
        </div>
      )}

      {actionsError && (
        <div className="panel" role="alert" style={{ marginBottom: 16 }}>
          <QueryErrorState
            error={actionsErrorDetail}
            onRetry={refetchActions}
            title="Workflow actions could not be loaded"
          />
        </div>
      )}

      <ActionCentreIntelStrip
        proposed={intel.proposed}
        savings={intel.savings}
        critical={intel.critical}
        open={intel.open || findingsTotal}
        currency={currency}
      />
      <ActionCentreCommandBar
        filters={filters}
        onFilter={handleFilter}
        onSearch={handleSearch}
        onClear={handleClear}
        visibleCount={visibleRows.length}
        totalCount={findingsTotal || allRows.length}
      />
      <ActionCentreFindingsTable
        rows={visibleRows}
        sort={sort}
        onSort={handleSort}
        totalCount={findingsTotal || allRows.length}
        truncated={truncated}
        hasActiveFilters={hasActiveFilters}
        emptyState={emptyState}
        isLoadingMore={resourcesLoading && !resources.length}
        currency={currency}
        onClearFilters={handleClear}
      />
    </section>
  );
}

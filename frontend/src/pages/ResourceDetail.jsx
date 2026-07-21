import React, {
  useCallback, useContext, useEffect, useMemo,
} from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import useFindingsIndex from '../hooks/useFindingsIndex';
import useOptimizationActions from '../hooks/useOptimizationActions';
import usePaginatedResources from '../hooks/usePaginatedResources';
import useAdvisorIndex from '../hooks/useAdvisorIndex';
import { fetchBilledResourceProperties, fetchDashboardSyncStatus } from '../api/azure';
import { normalizeArmId } from '../utils/findingDedupe';
import { INVENTORY_API_PATH, resourceRowId } from '../utils/resourceRowId';
import { resolveSubscriptionLabel } from '../utils/subscriptionDisplay';
import { ACTION_INDEX_LIMIT } from '../utils/actionUtils';
import {
  buildFindingTableRows,
  decodeResourceRouteId,
  encodeResourceRouteId,
  filterFindingRows,
  loadAcFiltersState,
  sortFindingRows,
  DEFAULT_AC_SORT,
} from '../utils/actionCentreV2Utils';
import { buildInsightData } from '../utils/insightCanvasUtils';
import { DiskInsightCanvas, isDiskCanonicalType } from '../disks';
import { lookupAdvisorForResource } from '../utils/resourceAdvisorUtils';
import useDrawerResourceBundle from '../hooks/useDrawerResourceBundle';
import useResourceAnalysisOnOpen from '../hooks/useResourceAnalysisOnOpen';
import InsightCanvasBar from '../components/insight-canvas/InsightCanvasBar';
import InsightCanvasLayout from '../components/insight-canvas/InsightCanvasLayout';
import { SubscriptionRequired, QueryErrorState, LoadingState } from '../components/QueryStates';

export default function ResourceDetail() {
  const { resourceId: encodedId } = useParams();
  const navigate = useNavigate();
  const { subscription, subscriptionOptions, billingCurrency } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const currency = billingCurrency || 'CAD';
  const subscriptionLabel = resolveSubscriptionLabel(subscription, subscriptionOptions);
  const resourceId = decodeResourceRouteId(encodedId);
  const normalizedId = normalizeArmId(resourceId);
  const isDiskId = normalizedId.toLowerCase().includes('/disks/');

  const saved = loadAcFiltersState();
  const sort = saved?.sort || DEFAULT_AC_SORT;
  const filters = saved?.filters;

  const {
    findings,
    byResourceId,
    isLoading: findingsLoading,
    isError: findingsError,
    error: findingsErrorDetail,
    refetch: refetchFindings,
  } = useFindingsIndex(subscription, { inventoryOnly: false });

  const {
    items: resources,
    isLoading: resourcesLoading,
    refetch: refetchResources,
  } = usePaginatedResources({
    apiPath: INVENTORY_API_PATH,
    subscription,
    enabled: !!subscription && !isDiskId,
    inventoryOnly: true,
  });

  const {
    items: diskResources,
    isLoading: disksLoading,
    refetch: refetchDisks,
  } = usePaginatedResources({
    apiPath: '/resources/disks',
    subscription,
    enabled: !!subscription && isDiskId,
    includeMetrics: true,
    includeCosts: true,
  });

  const { items: actions, refetch: refetchActions } = useOptimizationActions(
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

  const { byResourceId: advisorByResourceId } = useAdvisorIndex(subscription);

  const resourceRow = useMemo(() => {
    const pool = isDiskId ? diskResources : resources;
    return (pool || []).find((r) => normalizeArmId(resourceRowId(r)) === normalizedId);
  }, [isDiskId, diskResources, resources, normalizedId]);

  const resourceFindings = useMemo(
    () => byResourceId.get(normalizedId) || [],
    [byResourceId, normalizedId],
  );

  const primaryFinding = resourceFindings[0] || null;

  const resourceActions = useMemo(
    () => (actions || []).filter((a) => normalizeArmId(a.resource_id) === normalizedId),
    [actions, normalizedId],
  );

  const { data: propertiesPayload, isLoading: propertiesLoading } = useQuery({
    queryKey: ['resource-properties', subscription, normalizedId],
    queryFn: () => fetchBilledResourceProperties({
      subscription_id: subscription,
      resource_id: normalizedId,
    }),
    enabled: Boolean(subscription && normalizedId),
    staleTime: 120_000,
  });

  const metricsTimespan = 'P7D';
  const shouldLoadBundle = Boolean(subscription && normalizedId);

  useResourceAnalysisOnOpen({
    subscriptionId: subscription,
    resourceId: normalizedId,
    enabled: shouldLoadBundle,
  });

  const {
    data: resourceBundle,
    isLoading: bundleLoading,
    isFetching: bundleFetching,
    isError: bundleError,
  } = useDrawerResourceBundle({
    subscriptionId: subscription,
    resourceId: normalizedId,
    timespan: metricsTimespan,
    enabled: shouldLoadBundle,
  });

  const bundlePending = bundleLoading || (bundleFetching && !resourceBundle);

  const advisorItems = useMemo(
    () => lookupAdvisorForResource(advisorByResourceId, resourceRow || { id: normalizedId }),
    [advisorByResourceId, resourceRow, normalizedId],
  );

  const insightData = useMemo(() => {
    if (!resourceRow && !primaryFinding) return null;
    return buildInsightData({
      finding: primaryFinding,
      findings: resourceFindings,
      row: resourceRow,
      actions: resourceActions,
      propertiesPayload,
      advisorItems,
      metricsData: resourceBundle?.metrics || null,
      advancedAnalysis: resourceBundle?.advanced_analysis || null,
      metricsLoading: bundlePending,
      metricsError: bundleError,
      metricsTimespan,
      subscriptionLabel,
      subscriptionId: subscription,
      resourceId: normalizedId,
      currency,
      analyzedAt: syncStatus?.analysis?.last_job_at || syncStatus?.last_analysis_at,
    });
  }, [
    primaryFinding,
    resourceFindings,
    resourceRow,
    resourceActions,
    propertiesPayload,
    advisorItems,
    resourceBundle,
    bundlePending,
    bundleError,
    metricsTimespan,
    subscriptionLabel,
    subscription,
    normalizedId,
    currency,
    syncStatus,
  ]);

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

  const queueRows = useMemo(() => {
    const rows = buildFindingTableRows({
      findings,
      resourceById,
      actionsByResource,
      currency,
      subscriptionLabel,
    });
    const filtered = filters ? filterFindingRows(rows, filters) : rows;
    return sortFindingRows(filtered, sort);
  }, [findings, resourceById, actionsByResource, currency, subscriptionLabel, filters, sort]);

  const queueIndex = queueRows.findIndex((r) => normalizeArmId(r.resourceId) === normalizedId);
  const positionLabel = queueIndex >= 0
    ? `${queueIndex + 1} of ${queueRows.length}`
    : '—';

  const goToRow = useCallback((row) => {
    if (!row?.resourceId) return;
    navigate(`/resource/${encodeResourceRouteId(row.resourceId)}`);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [navigate]);

  const goPrev = useCallback(() => {
    if (queueIndex > 0) goToRow(queueRows[queueIndex - 1]);
  }, [queueIndex, queueRows, goToRow]);

  const goNext = useCallback(() => {
    if (queueIndex >= 0 && queueIndex < queueRows.length - 1) {
      goToRow(queueRows[queueIndex + 1]);
    }
  }, [queueIndex, queueRows, goToRow]);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'ArrowLeft') { e.preventDefault(); goPrev(); }
      if (e.key === 'ArrowRight') { e.preventDefault(); goNext(); }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [goPrev, goNext]);

  if (!subscription) {
    return (
      <section className="ic-detail" aria-label="Resource analysis">
        <SubscriptionRequired />
      </section>
    );
  }

  if (findingsError) {
    return (
      <section className="ic-detail" aria-label="Resource analysis">
        <QueryErrorState
          error={findingsErrorDetail}
          onRetry={() => { refetchFindings(); refetchResources(); refetchDisks(); refetchActions(); }}
        />
      </section>
    );
  }

  if ((findingsLoading || resourcesLoading || disksLoading || propertiesLoading) && !insightData) {
    return (
      <section className="ic-detail" aria-label="Resource analysis">
        <LoadingState message="Loading resource analysis…" />
      </section>
    );
  }

  if (!insightData) {
    return (
      <section className="ic-detail" aria-label="Resource analysis">
        <p className="ac-empty">Resource not found in the current subscription.</p>
      </section>
    );
  }

  const isDiskResource = isDiskId || isDiskCanonicalType(resourceRow?.type);

  if (isDiskResource) {
    return (
      <DiskInsightCanvas
        data={insightData}
        positionLabel={positionLabel}
        onPrev={goPrev}
        onNext={goNext}
        prevDisabled={queueIndex <= 0}
        nextDisabled={queueIndex < 0 || queueIndex >= queueRows.length - 1}
        subscriptionId={subscription}
        isAdmin={isAdmin}
        currency={currency}
      />
    );
  }

  return (
    <section className="ic-detail" aria-label="Resource analysis">
      <InsightCanvasBar
        data={insightData}
        positionLabel={positionLabel}
        onPrev={goPrev}
        onNext={goNext}
        prevDisabled={queueIndex <= 0}
        nextDisabled={queueIndex < 0 || queueIndex >= queueRows.length - 1}
        subscriptionId={subscription}
        isAdmin={isAdmin}
        currency={currency}
      />
      <InsightCanvasLayout data={insightData} />
    </section>
  );
}

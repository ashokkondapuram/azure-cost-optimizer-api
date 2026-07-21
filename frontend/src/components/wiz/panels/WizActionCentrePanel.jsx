import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppCtx } from '../../../App';
import { useAuth } from '../../../context/AuthContext';
import usePaginatedResources from '../../../hooks/usePaginatedResources';
import useFindingsIndex from '../../../hooks/useFindingsIndex';
import useOptimizationActions from '../../../hooks/useOptimizationActions';
import useResourceRecommendationsIndex from '../../../hooks/useResourceRecommendationsIndex';
import { fetchBilledResourceProperties } from '../../../api/azure';
import ResourceInsightDrawer from '../../ResourceInsightDrawer';
import OptimizationActionChip from '../../optimization/OptimizationActionChip';
import WizCommandBar from '../WizCommandBar';
import {
  LoadingState, EmptyState, QueryErrorState,
} from '../../QueryStates';
import { formatCurrency } from '../../../utils/format';
import AssetIcon from '../../AssetIcon';
import { iconForRow, serviceDisplayNameForRow } from '../../../config/assetIcons';
import { resourceTotalCost, resourceBilledMtd, resourceRetailMonthly, resourceRetailCurrency } from '../../../utils/costCurrency';
import { resolveResourceFindings } from '../../../utils/resourceFindingsUtils';
import { RESOURCE_PAGES } from '../../../config/appRegistry';
import { resourceRowId, INVENTORY_API_PATH } from '../../../utils/resourceRowId';
import { normalizeArmId } from '../../../utils/findingDedupe';
import {
  countDistinctActionResources,
  uniqueActionTypes,
} from '../../../utils/actionUtils';
import WizFilteredSavingsCharts from '../charts/WizFilteredSavingsCharts';
import WizResourceNameLink from '../WizResourceNameLink';
import OptimizationGroupPanel from '../../optimization/OptimizationGroupPanel';
import {
  compareResourceRowsByPriority,
  groupResourceRows,
  orderedBreakdownFromSummary,
  resourceGroupLabelFromRow,
} from '../../../utils/taxonomy';
import WizGroupBySelect from '../WizGroupBySelect';
import ActionWorkflowButtons from '../../optimization/ActionWorkflowButtons';
import { isInventoryResource } from '../../../utils/inventoryResource';
import { isActionCentreFinding } from '../../../utils/findingFilters';
import { classifyFindingSourceKey, sourceBreakdownOrdered } from '../../../utils/findingsSummaryUtils';
import RecommendationHelpTooltip from '../../RecommendationHelpTooltip';
import {
  buildActionCentreRowDisplay,
  categoryLabelForRec,
  resourceMetaLine,
} from '../../../utils/actionCentreRowUtils';
import {
  matchesActionCentreCategory,
  matchesActionCentreResourcePage,
} from '../../../utils/actionCentreResourceFilter';

const API_PATH = INVENTORY_API_PATH;

function resourceId(row) {
  return resourceRowId(row);
}

function renderActionCentreRow({
  row,
  rec,
  rid,
  selected,
  hydratingId,
  currency,
  subscription,
  isAdmin,
  sourceLabels,
  handleSelectRow,
}) {
  const isSelected = selected && resourceId(selected) === rid;
  const isHydrating = hydratingId === rid;
  const display = buildActionCentreRowDisplay(rec, sourceLabels);
  const sev = display.severity;
  const priorityClass = sev === 'CRITICAL'
    ? 'wiz-row--priority-critical'
    : sev === 'HIGH'
      ? 'wiz-row--priority-high'
      : '';
  const armId = rid || row.id || row.resource_id || '';
  return (
    <tr
      key={rid || row.name}
      className={`${isSelected ? 'wiz-row--selected' : ''} ${priorityClass}`.trim()}
      onClick={() => handleSelectRow(row)}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleSelectRow(row);
        }
      }}
    >
      <td>
        <div className="wiz-resource-cell" title={armId || undefined}>
          <AssetIcon iconKey={iconForRow(row, { apiPath: API_PATH })} size={20} />
          <div style={{ minWidth: 0 }}>
            <div className="wiz-resource-cell__name">
              <WizResourceNameLink resourceId={armId} name={row.name}>
                {row.name}
                {isHydrating && <span style={{ marginLeft: 6, opacity: 0.6 }}>…</span>}
              </WizResourceNameLink>
            </div>
            <div className="wiz-resource-cell__meta">
              {resourceMetaLine(row)}
            </div>
          </div>
        </div>
      </td>
      <td className="wiz-service-cell">{serviceDisplayNameForRow(row) || '—'}</td>
      <td className="wiz-category-cell">{categoryLabelForRec(rec)}</td>
      <td className="wiz-cost-cell">
        {(() => {
          const billed = resourceBilledMtd(row);
          const retail = resourceRetailMonthly(row);
          const retailCurrency = resourceRetailCurrency(row, currency);
          if (billed <= 0 && retail <= 0) return '—';
          return (
            <span className="wiz-cost-cell__stack">
              {billed > 0 && (
                <span title="Month to date (billed)">
                  {formatCurrency(billed, { currency, decimals: 0 })}
                </span>
              )}
              {retail > 0 && (
                <span
                  className="wiz-cost-cell__retail"
                  title="Catalog pricing from Azure Retail Prices — estimated monthly, not your invoice."
                >
                  Retail
                  {' '}
                  {formatCurrency(retail, { currency: retailCurrency, decimals: 0 })}
                </span>
              )}
            </span>
          );
        })()}
      </td>
      <td className="wiz-rec-cell">
        {display.finding ? (
          <RecommendationHelpTooltip
            finding={display.finding}
            block
            compact
            detailHint="View details in drawer"
          >
            <div className="wiz-rec-cell__stack">
              <span className="wiz-rec-cell__headline">
                {display.sourceBadge && (
                  <span
                    className={`wiz-source-badge wiz-source-badge--${display.sourceKey}`}
                    aria-label={`Source: ${display.sourceBadge}`}
                  >
                    {display.sourceBadge}
                  </span>
                )}
                <span className={`wiz-sev-dot wiz-sev-dot--${display.severity}`} aria-hidden />
                <span className="wiz-rec-cell__headline-text">{display.headline}</span>
              </span>
              {display.secondaryLine && (
                <span className="wiz-rec-cell__secondary">{display.secondaryLine}</span>
              )}
            </div>
          </RecommendationHelpTooltip>
        ) : '—'}
      </td>
      <td className={`wiz-savings-cell${rec.savings > 0 ? ' wiz-savings-cell--positive' : ''}`}>
        {rec.savings > 0
          ? formatCurrency(rec.savings, { currency, decimals: 0 })
          : '—'}
      </td>
      <td className="wiz-action-cell">
        {rec.topAction ? (
          <OptimizationActionChip actionType={rec.topAction.action_type} />
        ) : (
          <span className="wiz-pill wiz-pill--muted">—</span>
        )}
      </td>
      <td className="wiz-action-centre-review-col">
        {(() => {
          const proposed = rec.proposedActions?.length
            ? [...rec.proposedActions].sort(
              (a, b) => (b.estimated_monthly_savings || 0) - (a.estimated_monthly_savings || 0),
            )[0]
            : null;
          if (!proposed) return <span className="wiz-pill wiz-pill--muted">—</span>;
          return (
            <ActionWorkflowButtons
              action={proposed}
              subscriptionId={subscription}
              isAdmin={isAdmin}
              currency={currency}
              variant="compact"
            />
          );
        })()}
      </td>
    </tr>
  );
}

export default function WizActionCentrePanel({
  resourceTypeFilter = '',
  resourceIdFilter = '',
  initialSearch = '',
  inspectOnLoad = false,
  inspectSection = 'advanced-analysis',
  initialHasAction = false,
  actions: actionsProp = [],
  actionsSummary = {},
  actionsError: actionsErrorProp = false,
  actionsErrorDetail: actionsErrorDetailProp = null,
  refetchActions: refetchActionsProp,
  onInventoryTotalChange,
}) {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const currency = billingCurrency || 'CAD';
  const [q, setQ] = useState(initialSearch);
  const [selected, setSelected] = useState(null);
  const [hydratingId, setHydratingId] = useState(null);
  const [recommendationsOnly, setRecommendationsOnly] = useState(false);
  const [filterCritical, setFilterCritical] = useState(false);
  const [filterHighSavings, setFilterHighSavings] = useState(false);
  const [filterHasAction, setFilterHasAction] = useState(initialHasAction);
  const [filterAnySavings, setFilterAnySavings] = useState(false);
  const [filterMediumSeverity, setFilterMediumSeverity] = useState(false);
  const [filterNoIssues, setFilterNoIssues] = useState(false);
  const [actionTypeFilter, setActionTypeFilter] = useState('');
  const [sortBy, setSortBy] = useState('priority');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [groupBy, setGroupBy] = useState('');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [serviceFilter, setServiceFilter] = useState('');
  const deepLinkHandled = useRef(false);

  const pageFilter = resourceTypeFilter
    ? RESOURCE_PAGES[resourceTypeFilter]
    : null;

  const {
    items: data,
    total,
    isLoading,
    isError,
    error,
    refetch,
    hasMore,
    loadMore,
    isLoadingMore,
  } = usePaginatedResources({
    apiPath: API_PATH,
    subscription,
    enabled: !!subscription,
    inventoryOnly: true,
  });

  const {
    byResourceId,
    savingsByResource,
    summary: findingsSummary,
    findings,
    indexReady,
    truncated,
    findingsTotal,
    isLoading: findingsLoading,
    isError: findingsError,
    error: findingsErrorDetail,
    refetch: refetchFindings,
  } = useFindingsIndex(subscription, { inventoryOnly: true });

  const effectiveSummary = findingsSummary;
  const sourceLabels = effectiveSummary?.source_labels || {};
  const sourceBreakdown = useMemo(
    () => sourceBreakdownOrdered(effectiveSummary),
    [effectiveSummary],
  );
  const categoryBreakdown = useMemo(
    () => orderedBreakdownFromSummary(effectiveSummary, 'by_category_ordered'),
    [effectiveSummary],
  );

  const { items: actionsFallback, isLoading: actionsLoadingFallback, isError: actionsFallbackError, error: actionsFallbackErrorDetail, refetch: refetchActionsFallback } = useOptimizationActions(
    subscription,
    { inventory_only: true },
  );
  const actions = actionsProp.length ? actionsProp : actionsFallback;
  const actionsLoading = actionsProp.length ? false : actionsLoadingFallback;
  const actionsError = actionsProp.length ? actionsErrorProp : actionsFallbackError;
  const actionsErrorDetail = actionsProp.length ? actionsErrorDetailProp : actionsFallbackErrorDetail;
  const refetchActions = actionsProp.length ? refetchActionsProp : refetchActionsFallback;

  const proposedActions = useMemo(
    () => actions.filter((a) => (a.workflow_status || 'proposed') === 'proposed'),
    [actions],
  );

  const proposedResourceCount = useMemo(
    () => countDistinctActionResources(proposedActions),
    [proposedActions],
  );

  const actionTypes = useMemo(() => uniqueActionTypes(proposedActions), [proposedActions]);

  const { enrich, proposedResourceIds, hasProposedAction } = useResourceRecommendationsIndex({
    byResourceId,
    savingsByResource,
    actions,
    indexReady,
  });

  const services = useMemo(() => {
    const set = new Set();
    for (const row of data) {
      const service = serviceDisplayNameForRow(row);
      if (service) set.add(service);
    }
    return [...set].sort();
  }, [data]);

  const enrichedRows = useMemo(() => {
    const byId = new Map();
    for (const row of data || []) {
      if (!isInventoryResource(row)) continue;
      const rid = resourceId(row);
      if (!rid) continue;
      byId.set(rid, { row, rec: enrich(rid) });
    }
    return [...byId.values()];
  }, [data, enrich]);

  const chipCounts = useMemo(() => {
    if (indexReady) {
      let critical = 0;
      let highSav = 0;
      let medium = 0;
      let anySavings = 0;
      const withRecIds = new Set();
      for (const [resourceKey, resourceFindings] of byResourceId.entries()) {
        withRecIds.add(resourceKey);
        const top = resourceFindings[0];
        const sev = top?.severity;
        if (sev === 'CRITICAL' || sev === 'HIGH') critical += 1;
        if (sev === 'MEDIUM') medium += 1;
        const savings = savingsByResource.get(resourceKey) || 0;
        if (savings >= 100) highSav += 1;
        if (savings > 0) anySavings += 1;
      }
      for (const resourceKey of proposedResourceIds) {
        withRecIds.add(resourceKey);
      }
      const withRec = withRecIds.size;
      return {
        critical,
        highSav,
        withRec,
        withAction: proposedResourceCount || proposedResourceIds.size,
        anySavings,
        medium,
        noIssues: Math.max(0, (total || 0) - withRec),
        proposedTotal: actionsSummary?.proposed ?? proposedActions.length,
      };
    }
    let critical = 0;
    let highSav = 0;
    let withRec = 0;
    let anySavings = 0;
    let medium = 0;
    let noIssues = 0;
    for (const { rec } of enrichedRows) {
      if (rec.hasRecommendations) withRec += 1;
      if (!rec.hasRecommendations) noIssues += 1;
      const sev = rec.topFinding?.severity;
      if (sev === 'CRITICAL' || sev === 'HIGH') critical += 1;
      if (sev === 'MEDIUM') medium += 1;
      if (rec.savings >= 100) highSav += 1;
      if (rec.savings > 0) anySavings += 1;
    }
    return {
      critical,
      highSav,
      withRec,
      withAction: proposedResourceCount || proposedResourceIds.size,
      anySavings,
      medium,
      noIssues,
      proposedTotal: actionsSummary?.proposed ?? proposedActions.length,
    };
  }, [
    indexReady,
    byResourceId,
    savingsByResource,
    proposedResourceIds,
    total,
    enrichedRows,
    proposedResourceCount,
    actionsSummary,
    proposedActions.length,
  ]);

  const rows = useMemo(() => {
    let list = enrichedRows;
    if (pageFilter) {
      list = list.filter(({ row }) => matchesActionCentreResourcePage(row, pageFilter));
    }
    if (serviceFilter) {
      list = list.filter(({ row: r }) => serviceDisplayNameForRow(r) === serviceFilter);
    }
    if (recommendationsOnly) {
      list = list.filter(({ rec }) => rec.hasRecommendations);
    }
    if (filterCritical) {
      list = list.filter(({ rec }) => ['CRITICAL', 'HIGH'].includes(rec.topFinding?.severity));
    }
    if (filterHighSavings) {
      list = list.filter(({ rec }) => rec.savings >= 100);
    }
    if (filterAnySavings) {
      list = list.filter(({ rec }) => rec.savings > 0);
    }
    if (filterMediumSeverity) {
      list = list.filter(({ rec }) => rec.topFinding?.severity === 'MEDIUM');
    }
    if (filterNoIssues) {
      list = list.filter(({ rec }) => !rec.hasRecommendations);
    }
    if (filterHasAction) {
      list = list.filter(({ row, rec }) => (
        hasProposedAction(resourceId(row)) || (rec.proposedActions?.length > 0)
      ));
    }
    if (actionTypeFilter) {
      list = list.filter(({ rec }) => rec.proposedActions?.some(
        (a) => a.action_type === actionTypeFilter,
      ) || rec.topAction?.action_type === actionTypeFilter);
    }
    if (categoryFilter) {
      list = list.filter(({ row, rec }) => matchesActionCentreCategory(row, rec, categoryFilter));
    }
    if (sourceFilter) {
      list = list.filter(({ rec }) => rec.findings.some(
        (f) => isActionCentreFinding(f) && classifyFindingSourceKey(f) === sourceFilter,
      ));
    }
    if (q.trim()) {
      const hay = q.trim().toLowerCase();
      list = list.filter(({ row: r }) => {
        const text = `${r.name} ${r.id} ${serviceDisplayNameForRow(r)} ${r.type} ${resourceGroupLabelFromRow(r)}`.toLowerCase();
        return text.includes(hay);
      });
    }
    const sorted = [...list];
    sorted.sort((a, b) => {
      if (sortBy === 'priority') return compareResourceRowsByPriority(a, b);
      if (sortBy === 'cost') {
        return resourceTotalCost(b.row, currency) - resourceTotalCost(a.row, currency);
      }
      if (sortBy === 'name') {
        return (a.row.name || '').localeCompare(b.row.name || '');
      }
      if (sortBy === 'issues') {
        return b.rec.findingCount - a.rec.findingCount;
      }
      return b.rec.savings - a.rec.savings;
    });
    return sorted;
  }, [
    enrichedRows, q, serviceFilter, recommendationsOnly, filterCritical,
    filterHighSavings, filterAnySavings, filterMediumSeverity, filterNoIssues,
    filterHasAction, actionTypeFilter, categoryFilter, sourceFilter, pageFilter, sortBy, currency, hasProposedAction,
  ]);

  const groupedRows = useMemo(
    () => groupResourceRows(rows, groupBy),
    [groupBy, rows],
  );

  const filteredSavings = useMemo(
    () => rows.reduce((sum, { rec }) => sum + (rec.savings || 0), 0),
    [rows],
  );

  const hasActiveFilters = Boolean(
    q.trim()
    || serviceFilter
    || recommendationsOnly
    || filterCritical
    || filterHighSavings
    || filterAnySavings
    || filterMediumSeverity
    || filterNoIssues
    || filterHasAction
    || actionTypeFilter
    || categoryFilter
    || sourceFilter
    || pageFilter,
  );

  const drawerFocusSection = inspectOnLoad ? inspectSection : 'overview';

  const handleCloseDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSelected(null);
    setHydratingId(null);
  }, []);

  const handleSelectRow = async (row) => {
    setSelected(row);
    setDrawerOpen(true);
    const rid = resourceId(row);
    if (!subscription || !rid || row.inInventory) return;
    setHydratingId(rid);
    try {
      const payload = await fetchBilledResourceProperties({
        subscription_id: subscription,
        resource_id: row.id || row.resource_id,
      });
      const hydrated = payload?.resource;
      if (hydrated) {
        setSelected((current) => {
          if (!current || resourceId(current) !== rid) return current;
          return { ...current, ...hydrated };
        });
      }
    } catch {
      /* drawer still opens with cost data */
    } finally {
      setHydratingId(null);
    }
  };

  useEffect(() => {
    setQ(initialSearch || '');
  }, [initialSearch]);

  useEffect(() => {
    setFilterHasAction(initialHasAction);
  }, [initialHasAction]);

  useEffect(() => {
    if (typeof onInventoryTotalChange === 'function') {
      onInventoryTotalChange(total);
    }
  }, [total, onInventoryTotalChange]);

  useEffect(() => {
    if (!resourceIdFilter || deepLinkHandled.current || !subscription) return;
    const target = normalizeArmId(resourceIdFilter);
    const match = data.find((row) => resourceId(row) === target);
    if (match) {
      deepLinkHandled.current = true;
      handleSelectRow(match);
      return;
    }
    if (!isLoading && data.length > 0) {
      deepLinkHandled.current = true;
      (async () => {
        try {
          const payload = await fetchBilledResourceProperties({
            subscription_id: subscription,
            resource_id: resourceIdFilter,
          });
          const hydrated = payload?.resource;
          if (hydrated) {
            setSelected(hydrated);
            setDrawerOpen(true);
            setQ(hydrated.name || '');
          }
        } catch {
          /* resource may not be in billed inventory */
        }
      })();
    }
  }, [resourceIdFilter, subscription, data, isLoading]);

  const drawerFindings = useMemo(() => {
    if (!selected) return [];
    return resolveResourceFindings(
      selected,
      byResourceId.get(resourceId(selected)) || [],
      { indexReady },
    );
  }, [selected, byResourceId, indexReady]);

  if (!subscription) {
    return (
      <div className="wiz-empty">
        <strong>Select a subscription</strong>
        Browse all resources with open findings and analysis in one place.
      </div>
    );
  }

  const loading = isLoading;
  const findingsPending = findingsLoading || actionsLoading;
  const analysisPartialFailure = !isError && !loading && (findingsError || actionsError);
  const analysisFailed = findingsError && actionsError;

  return (
    <div className="wiz-panel" id="wiz-panel-action-centre">
      <div className="wiz-action-centre-table">
        <section className="wiz-card wiz-card--full">
          <header className="wiz-card__head">
            <h3>
              {pageFilter
                ? pageFilter.title
                : filterHasAction
                  ? 'Proposed actions'
                  : 'All resources'}
            </h3>
            <span className="wiz-pill">
              {rows.length.toLocaleString()} shown
              {total > rows.length ? ` · ${total.toLocaleString()} total` : ''}
            </span>
          </header>

          <WizCommandBar
            search={q}
            onSearchChange={setQ}
            searchPlaceholder="Search by name, type, resource group…"
            sort={sortBy}
            onSortChange={setSortBy}
            sortOptions={[
              { value: 'priority', label: 'Sort: priority' },
              { value: 'savings', label: 'Sort: savings' },
              { value: 'cost', label: 'Sort: cost' },
              { value: 'issues', label: 'Sort: issues' },
              { value: 'name', label: 'Sort: name' },
            ]}
            chips={[
              {
                id: 'recs',
                label: 'With findings',
                count: chipCounts.withRec,
                active: recommendationsOnly,
                onClick: () => setRecommendationsOnly((v) => !v),
              },
              {
                id: 'critical',
                label: 'Critical / high',
                count: chipCounts.critical,
                active: filterCritical,
                onClick: () => setFilterCritical((v) => !v),
              },
              {
                id: 'savings',
                label: 'Savings $100+',
                count: chipCounts.highSav,
                active: filterHighSavings,
                onClick: () => setFilterHighSavings((v) => !v),
              },
              {
                id: 'actions',
                label: 'Has proposed action',
                count: chipCounts.withAction,
                active: filterHasAction,
                onClick: () => setFilterHasAction((v) => !v),
              },
              {
                id: 'any-savings',
                label: 'Any savings',
                count: chipCounts.anySavings,
                active: filterAnySavings,
                onClick: () => setFilterAnySavings((v) => !v),
              },
              {
                id: 'medium',
                label: 'Medium severity',
                count: chipCounts.medium,
                active: filterMediumSeverity,
                onClick: () => setFilterMediumSeverity((v) => !v),
              },
              {
                id: 'clean',
                label: 'No open issues',
                count: chipCounts.noIssues,
                active: filterNoIssues,
                onClick: () => setFilterNoIssues((v) => !v),
              },
            ]}
          >
            {!pageFilter && (
              <select
                className="wiz-command-select"
                value={serviceFilter}
                onChange={(e) => setServiceFilter(e.target.value)}
                aria-label="Service"
              >
                <option value="">All services</option>
                {services.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            )}
            {actionTypes.length > 0 && (
              <select
                className="wiz-command-select"
                value={actionTypeFilter}
                onChange={(e) => setActionTypeFilter(e.target.value)}
                aria-label="Action type"
              >
                <option value="">All action types</option>
                {actionTypes.map((t) => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            )}
            {sourceBreakdown.length > 0 && (
              <select
                className="wiz-command-select"
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
                aria-label="Finding source"
              >
                <option value="">All sources</option>
                {sourceBreakdown.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                    {' '}
                    (
                    {item.count.toLocaleString()}
                    )
                  </option>
                ))}
              </select>
            )}
            <WizGroupBySelect value={groupBy} onChange={setGroupBy} />
          </WizCommandBar>

          {categoryBreakdown.length > 0 && (
            <div className="wiz-category-chips" role="group" aria-label="Filter by category">
              <button
                type="button"
                className={`wiz-pill${!categoryFilter ? ' wiz-pill--ok' : ''}`}
                onClick={() => setCategoryFilter('')}
              >
                All categories
              </button>
              {categoryBreakdown.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`wiz-pill${categoryFilter === item.key ? ' wiz-pill--ok' : ''}`}
                  onClick={() => setCategoryFilter((current) => (
                    current === item.key ? '' : item.key
                  ))}
                >
                  {item.label}
                  {' '}
                  <span className="wiz-pill__count">{item.count}</span>
                </button>
              ))}
            </div>
          )}

          {hasActiveFilters && rows.length > 0 && (
            <WizFilteredSavingsCharts
              rows={rows}
              currency={currency}
              filteredSavings={filteredSavings}
            />
          )}

          {hasActiveFilters && rows.length > 0 && (
            <div className="wiz-results-summary wiz-results-summary--filtered" role="status">
              <span>
                <strong>{rows.length.toLocaleString()}</strong>
                {' '}
                resources match filters
              </span>
              <span className="wiz-results-summary__savings">
                {formatCurrency(filteredSavings, { currency, decimals: 0 })}
                {' '}
                recoverable/mo in view
              </span>
            </div>
          )}

          {truncated && (
            <div className="wiz-filter-summary" role="status" style={{ marginBottom: '0.65rem' }}>
              <span className="wiz-pill wiz-pill--warn">
                Loaded {findings.length.toLocaleString()} of {findingsTotal.toLocaleString()} open findings. Run filters or refresh data in Sync center.
              </span>
            </div>
          )}
          {findingsPending && !loading && (
            <p className="wiz-results-summary" role="status">Loading findings…</p>
          )}

          {analysisPartialFailure && (
            <div className="page-callout card page-callout--warn" role="alert">
              {findingsError && (
                <QueryErrorState
                  error={findingsErrorDetail}
                  onRetry={refetchFindings}
                  title="Could not load findings."
                />
              )}
              {actionsError && (
                <QueryErrorState
                  error={actionsErrorDetail}
                  onRetry={refetchActions}
                  title="Could not load proposed actions."
                />
              )}
              {!analysisFailed && (
                <p className="wiz-results-summary">
                  Inventory loaded, but analysis data is unavailable. You can still browse resources.
                </p>
              )}
            </div>
          )}

          {loading && <LoadingState message="Loading resources…" />}
          {isError && <QueryErrorState error={error} onRetry={refetch} />}
          {!loading && !isError && rows.length === 0 && (
            <EmptyState
              message={
                hasActiveFilters
                  ? 'No resources match your filters.'
                  : total === 0
                    ? 'No resources yet for this subscription. Run resource sync in Sync center, then sync costs and run analysis for findings.'
                    : 'No resources match your filters.'
              }
            />
          )}

          {!loading && !isError && rows.length > 0 && (
            <>
              <div className="wiz-table-wrap wiz-table-wrap--immersive">
                {groupedRows ? (
                  <div className="wiz-grouped-table">
                    {groupedRows.map((group) => (
                      <OptimizationGroupPanel
                        key={group.key}
                        groupKey={group.key}
                        title={group.label}
                        count={group.rows.length}
                        savings={group.savings}
                        currency={currency}
                        defaultOpen
                      >
                        <table className="wiz-table">
                          <thead>
                            <tr>
                              <th>Resource</th>
                              <th>Service</th>
                              <th>Category</th>
                              <th>Cost</th>
                              <th>Top recommendation</th>
                              <th>Savings</th>
                              <th>Action</th>
                              <th>Review</th>
                            </tr>
                          </thead>
                          <tbody>
                            {group.rows.map(({ row, rec }) => {
                              const rid = resourceId(row);
                              return renderActionCentreRow({
                                row,
                                rec,
                                rid,
                                selected,
                                hydratingId,
                                currency,
                                subscription,
                                isAdmin,
                                sourceLabels,
                                handleSelectRow,
                              });
                            })}
                          </tbody>
                        </table>
                      </OptimizationGroupPanel>
                    ))}
                  </div>
                ) : (
                  <table className="wiz-table">
                    <thead>
                      <tr>
                        <th>Resource</th>
                        <th>Service</th>
                        <th>Category</th>
                        <th>Cost</th>
                        <th>Top recommendation</th>
                        <th>Savings</th>
                        <th>Action</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(({ row, rec }) => {
                        const rid = resourceId(row);
                        return renderActionCentreRow({
                          row,
                          rec,
                          rid,
                          selected,
                          hydratingId,
                          currency,
                          subscription,
                          isAdmin,
                          sourceLabels,
                          handleSelectRow,
                        });
                      })}
                    </tbody>
                  </table>
                )}
              </div>
              {hasMore && (
                <div className="wiz-load-more">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => loadMore()}
                    disabled={isLoadingMore}
                  >
                    {isLoadingMore ? 'Loading…' : 'Load more'}
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {drawerOpen && selected && (
        <ResourceInsightDrawer
          resource={selected}
          apiPath={API_PATH}
          findings={drawerFindings}
          indexReady={indexReady}
          currency={currency}
          focusSection={drawerFocusSection}
          onClose={handleCloseDrawer}
        />
      )}
    </div>
  );
}

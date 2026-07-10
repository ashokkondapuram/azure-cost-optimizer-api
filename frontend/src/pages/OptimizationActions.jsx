import React, { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { useOptionalOptimizationHub } from '../context/OptimizationHubContext';
import useQueryWithTimeout from '../hooks/useQueryWithTimeout';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import FilterBar from '../components/FilterBar';
import FilterPresetsBar from '../components/filtering/FilterPresetsBar';
import BulkActionBar from '../components/BulkActionBar';
import SortableTableHeader from '../components/table/SortableTableHeader';
import VirtualizedTable from '../components/table/VirtualizedTable';
import ResponsiveTableWrapper from '../components/responsive/ResponsiveTableWrapper';
import useFilterPresets from '../hooks/useFilterPresets';
import { sortRows, toggleSort } from '../utils/clientSort';
import AdminOnly from '../components/AdminOnly';
import ActionApprovalModal from '../components/optimization/ActionApprovalModal';
import ActionTableRow from '../components/optimization/ActionTableRow';
import ActionLifecycle from '../components/optimization/ActionLifecycle';
import BulkAssignModal from '../components/optimization/BulkAssignModal';
import useOptimizationActions from '../hooks/useOptimizationActions';
import {
  bulkAssignOptimizationActions,
  bulkUpdateOptimizationActions,
  decideOptimizationActions,
  fetchOptimizationTrends,
  updateOptimizationAction,
} from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { formatCurrency } from '../utils/format';
import {
  actionTypeLabel,
  sumDistinctActionSavings,
  uniqueActionTypes,
  uniqueResourceTypes,
  workflowStatusLabel,
} from '../utils/actionUtils';
import {
  groupActionsByResourceGroup,
  groupActionsByResourceType,
  resourceGroupLabelForAction,
} from '../utils/optimizationGrouping';
import OptimizationGroupByToggle from '../components/optimization/OptimizationGroupByToggle';
import OptimizationGroupPanel from '../components/optimization/OptimizationGroupPanel';
import OptimizationHubTabShell from '../components/optimization/OptimizationHubTabShell';
import ResourceTableFooter from '../components/table/ResourceTableFooter';
import useOptimizationGroupBy from '../hooks/useOptimizationGroupBy';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import { PAGE_ICONS } from '../config/assetIcons';
import { SAVINGS_SCOPE, SAVINGS_METRIC_SUB } from '../config/savingsScope';

const STATUS_OPTIONS = ['proposed', 'approved', 'executed', 'rejected', 'deferred'];
const VIRTUAL_SCROLL_THRESHOLD = 20;
const MANY_ACTIONS_THRESHOLD = 35;
const ACTION_ROW_HEIGHT = 40;
const MAX_VIRTUAL_LIST_HEIGHT = 420;

export default function OptimizationActions({ embedded = false }) {
  const { subscription, currency } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const hub = useOptionalOptimizationHub();
  const embeddedHub = embedded ? hub : null;

  const [statusFilter, setStatusFilter] = useState(embeddedHub?.actionsStatus || '');
  const [actionTypeFilter, setActionTypeFilter] = useState('');
  const [resourceTypeFilter, setResourceTypeFilter] = useState('');
  const [search, setSearch] = useState('');
  const [groupBy, setGroupBy] = useOptimizationGroupBy('resource_type');
  const [selected, setSelected] = useState(new Set());
  const [reviewAction, setReviewAction] = useState(null);
  const [groupOpenState, setGroupOpenState] = useState({});
  const [sortKey, setSortKey] = useState('estimated_monthly_savings');
  const [sortDir, setSortDir] = useState('desc');
  const [showAssignModal, setShowAssignModal] = useState(false);

  useEffect(() => {
    if (!embeddedHub) return;
    setStatusFilter(embeddedHub.actionsStatus || '');
  }, [embeddedHub, embeddedHub?.actionsStatus]);

  const filterState = useMemo(() => ({
    statusFilter,
    actionTypeFilter,
    resourceTypeFilter,
    search,
  }), [statusFilter, actionTypeFilter, resourceTypeFilter, search]);

  const { presets, savePreset, deletePreset } = useFilterPresets('optimization-actions', filterState);

  const filters = useMemo(() => ({
    ...(statusFilter ? { workflow_status: statusFilter } : {}),
    ...(actionTypeFilter ? { action_type: actionTypeFilter } : {}),
    ...(resourceTypeFilter ? { resource_type: resourceTypeFilter } : {}),
  }), [statusFilter, actionTypeFilter, resourceTypeFilter]);

  const {
    items,
    summary,
    total,
    isLoading,
    isError,
    error,
    refetch,
    indexReady,
    loadMore,
    hasMore,
    isLoadingMore,
    loadedCount,
  } = useOptimizationActions(subscription, filters);

  const { data: trends } = useQueryWithTimeout({
    queryKey: ['optimization-trends', subscription],
    queryFn: () => fetchOptimizationTrends({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 120_000,
    timeout: 3000,
    allowEmpty: true,
  });

  const subscriptionSummary = useOptimizationActions(subscription, {}, {
    infinite: false,
    limit: 200,
  });

  const actionTypes = useMemo(
    () => uniqueActionTypes(subscriptionSummary.items),
    [subscriptionSummary.items],
  );
  const resourceTypes = useMemo(
    () => uniqueResourceTypes(subscriptionSummary.items),
    [subscriptionSummary.items],
  );

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((action) => {
      const haystack = [
        action.resource_name,
        action.resource_type,
        action.action_type,
        resourceGroupLabelForAction(action),
        action.resource_id,
      ].join(' ').toLowerCase();
      return haystack.includes(q);
    });
  }, [items, search]);

  const sortedItems = useMemo(() => sortRows(filteredItems, sortKey, sortDir, {
    estimated_monthly_savings: (row) => Number(row.estimated_monthly_savings) || 0,
    resource_name: (row) => row.resource_name || '',
    action_type: (row) => row.action_type || '',
    workflow_status: (row) => row.workflow_status || '',
    confidence: (row) => row.confidence || '',
  }), [filteredItems, sortKey, sortDir]);

  const distinctFilteredSavings = useMemo(
    () => sumDistinctActionSavings(sortedItems),
    [sortedItems],
  );

  const distinctSubscriptionSavings = useMemo(
    () => sumDistinctActionSavings(subscriptionSummary.items),
    [subscriptionSummary.items],
  );

  const groupedByType = useMemo(() => groupActionsByResourceType(sortedItems), [sortedItems]);
  const groupedByRg = useMemo(() => groupActionsByResourceGroup(sortedItems), [sortedItems]);

  const handleSort = (key) => {
    const next = toggleSort(sortKey, sortDir, key);
    setSortKey(next.key);
    setSortDir(next.direction);
  };

  const applyPreset = (preset) => {
    const f = preset.filters || {};
    const nextStatus = f.statusFilter || '';
    setStatusFilter(nextStatus);
    setActionTypeFilter(f.actionTypeFilter || '');
    setResourceTypeFilter(f.resourceTypeFilter || '');
    setSearch(f.search || '');
    if (embeddedHub) {
      embeddedHub.setActionsStatus(nextStatus);
    }
  };

  const handleSavePreset = () => {
    const name = window.prompt('Preset name');
    if (name) savePreset(name);
  };

  const handleStatusChange = (next) => {
    setStatusFilter(next);
    if (embeddedHub) {
      embeddedHub.setActionsStatus(next);
    }
  };

  const handleLifecycleClick = (stepId, filter) => {
    if (filter) {
      handleStatusChange(statusFilter === filter ? '' : filter);
    }
  };

  const clearFilters = () => {
    setStatusFilter('');
    setActionTypeFilter('');
    setResourceTypeFilter('');
    setSearch('');
    if (embeddedHub) embeddedHub.setActionsStatus('');
  };

  const decideMutation = useMutation({
    mutationFn: () => decideOptimizationActions({ subscription_id: subscription, force_refresh: false }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-actions'] });
      queryClient.invalidateQueries({ queryKey: ['optimization-trends'] });
      toast.success(`Generated ${data.total_actions || 0} actions`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const updateMutation = useMutation({
    mutationFn: ({ actionId, body }) => updateOptimizationAction(actionId, body, subscription),
    onSuccess: (_updated, vars) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-actions'] });
      queryClient.invalidateQueries({ queryKey: ['optimization-trends'] });
      const status = vars.body?.workflow_status;
      if (status) {
        toast.success(`Action marked ${workflowStatusLabel(status).toLowerCase()}`);
      } else if (vars.body?.owner || vars.body?.clear_owner) {
        toast.success('Owner updated');
      } else {
        toast.success('Note saved');
      }
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const bulkMutation = useMutation({
    mutationFn: ({ status, ids }) => bulkUpdateOptimizationActions({
      action_ids: ids,
      workflow_status: status,
    }, subscription),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-actions'] });
      queryClient.invalidateQueries({ queryKey: ['optimization-trends'] });
      setSelected(new Set());
      toast.success(`Updated ${vars.ids.length} actions`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const assignMutation = useMutation({
    mutationFn: ({ owner, ids }) => bulkAssignOptimizationActions({
      action_ids: ids,
      owner,
    }, subscription),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-actions'] });
      queryClient.invalidateQueries({ queryKey: ['optimization-trends'] });
      setSelected(new Set());
      setShowAssignModal(false);
      toast.success(`Assigned owner to ${data.updated || 0} actions`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === sortedItems.length) setSelected(new Set());
    else setSelected(new Set(sortedItems.map((a) => a.id)));
  };

  const openReview = useCallback((action, groupKey = null) => {
    setReviewAction(action);
    if (groupKey) {
      setGroupOpenState((prev) => ({ ...prev, [groupKey]: true }));
    }
  }, []);

  const closeReview = useCallback(() => setReviewAction(null), []);

  if (!subscription) return <SubscriptionRequired />;

  const manyActions = sortedItems.length >= MANY_ACTIONS_THRESHOLD;
  const workflowSummary = subscriptionSummary.summary || summary;
  const subscriptionTotal = subscriptionSummary.total ?? total;
  const subscriptionSavings = embeddedHub?.estimatedMonthlySavings
    ?? subscriptionSummary.totalSavings
    ?? distinctSubscriptionSavings;
  const filteredSavings = distinctFilteredSavings;
  const hasFilters = Boolean(statusFilter || actionTypeFilter || resourceTypeFilter || search);

  const isGroupOpen = (groupKey) => {
    if (groupOpenState[groupKey] !== undefined) return groupOpenState[groupKey];
    return !manyActions;
  };

  const setGroupOpen = (groupKey, nextOpen) => {
    setGroupOpenState((prev) => ({ ...prev, [groupKey]: nextOpen }));
  };

  const activeGroups = groupBy === 'resource_type'
    ? groupedByType
    : groupBy === 'resource_group'
      ? groupedByRg
      : [];

  const setAllGroupsOpen = (nextOpen) => {
    const next = {};
    activeGroups.forEach((group) => {
      next[group.key] = nextOpen;
    });
    setGroupOpenState(next);
  };

  const shouldVirtualizeRows = (rows) => rows.length >= VIRTUAL_SCROLL_THRESHOLD;

  const groupCountLabel = (group) => {
    const resources = group.resourceCount ?? group.items.length;
    const actions = group.items.length;
    if (actions === resources) {
      return `${actions} action${actions === 1 ? '' : 's'}`;
    }
    return `${resources} resources · ${actions} actions`;
  };

  const renderActionsTable = (rows, groupKey = null) => {
    const useVirtualScroll = shouldVirtualizeRows(rows);
    const virtualHeight = Math.min(MAX_VIRTUAL_LIST_HEIGHT, rows.length * ACTION_ROW_HEIGHT);
    const scrollableGroupBody = !useVirtualScroll && rows.length > 12;

    return (
      <ResponsiveTableWrapper>
        <div className={`table-wrap${scrollableGroupBody ? ' table-wrap--bounded' : ''}`}>
          <table className={`data-table actions-table actions-table--compact${isAdmin ? ' actions-table--with-select' : ''}${useVirtualScroll ? ' data-table--virtual-head' : ''}`}>
            <thead>
              <tr>
                {isAdmin && (
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={selected.size === sortedItems.length && sortedItems.length > 0}
                      onChange={toggleSelectAll}
                    />
                  </th>
                )}
                <SortableTableHeader sortKey="resource_name" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                  Resource
                </SortableTableHeader>
                <SortableTableHeader sortKey="action_type" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                  Action
                </SortableTableHeader>
                <SortableTableHeader sortKey="estimated_monthly_savings" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                  Est. savings
                </SortableTableHeader>
                <SortableTableHeader sortKey="workflow_status" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                  Status
                </SortableTableHeader>
                <th className="actions-table__review-col" aria-label="Actions" />
              </tr>
            </thead>
            {!useVirtualScroll ? (
              <tbody>
                {rows.map((action) => (
                  <tr
                    key={action.id}
                    className={`data-table__row--clickable${reviewAction?.id === action.id ? ' data-table__row--selected' : ''}`}
                    onClick={() => openReview(action, groupKey)}
                  >
                    <ActionTableRow
                      action={action}
                      currency={currency}
                      isAdmin={isAdmin}
                      selected={selected.has(action.id)}
                      isReviewing={reviewAction?.id === action.id}
                      onToggleSelect={toggleSelect}
                      onReview={(item) => openReview(item, groupKey)}
                    />
                  </tr>
                ))}
              </tbody>
            ) : null}
          </table>
          {useVirtualScroll && (
            <VirtualizedTable
              className={`virtual-table--actions${isAdmin ? '' : ' virtual-table--actions-no-select'}`}
              items={rows}
              rowHeight={ACTION_ROW_HEIGHT}
              height={virtualHeight}
            >
              {(action) => (
                <ActionTableRow
                  variant="virtual"
                  action={action}
                  currency={currency}
                  isAdmin={isAdmin}
                  selected={selected.has(action.id)}
                  isReviewing={reviewAction?.id === action.id}
                  onToggleSelect={toggleSelect}
                  onReview={(item) => openReview(item, groupKey)}
                />
              )}
            </VirtualizedTable>
          )}
        </div>
      </ResponsiveTableWrapper>
    );
  };

  const decideButton = (
    <AdminOnly>
      <button
        type="button"
        className="btn btn-primary btn-sm"
        disabled={decideMutation.isPending}
        onClick={() => decideMutation.mutate()}
      >
        <RefreshCw size={14} className={decideMutation.isPending ? 'spin' : ''} />
        Run decision engine
      </button>
    </AdminOnly>
  );

  return (
    <div className="page optimization-actions-page">
      {!embedded && (
        <PageHeader
          title="Optimization actions"
          subtitle="Review and approve synthesized actions from merged engine, Advisor, and metrics signals"
          iconKey={PAGE_ICONS.actions || 'recommendations'}
          actions={decideButton}
        />
      )}

      <OptimizationHubTabShell
        hero={(
          <PageHero
            variant="optimization-actions-hero"
            embedded={embedded}
            eyebrow="Decision engine"
            title="Optimization actions"
            subtitle="Each action combines engine findings, Azure Advisor, and utilization metrics into one recommendation."
            scopeNote={SAVINGS_SCOPE.hubActions}
            isLoading={isLoading && !items.length}
            metrics={[
              {
                label: 'Total',
                value: subscriptionTotal.toLocaleString(),
                tone: 'default',
                sub: 'All workflows',
              },
              {
                label: 'Proposed',
                value: (workflowSummary.proposed || 0).toLocaleString(),
                tone: 'warning',
                sub: 'Needs review',
                href: embedded ? '/optimization-hub?tab=actions&status=proposed' : undefined,
              },
              {
                label: 'Approved',
                value: (workflowSummary.approved || 0).toLocaleString(),
                tone: 'default',
                sub: 'Ready to execute',
              },
              {
                label: 'Est. savings',
                value: formatCurrency(subscriptionSavings, { currency, decimals: 0 }),
                tone: 'success',
                sub: SAVINGS_METRIC_SUB.unified,
              },
            ]}
            actions={isAdmin ? [{
              id: 'decide',
              label: decideMutation.isPending ? 'Running…' : 'Run decision engine',
              onClick: () => decideMutation.mutate(),
              disabled: decideMutation.isPending,
              primary: true,
              icon: <RefreshCw size={14} className={decideMutation.isPending ? 'spin' : ''} />,
            }] : []}
            footer={(
              <ActionLifecycle
                counts={workflowSummary}
                inObservation={trends?.rollout?.in_observation ?? 0}
                currency={currency}
                savings={subscriptionSavings}
                activeFilter={statusFilter}
                onStepClick={handleLifecycleClick}
                compact
                className="optimization-actions-lifecycle"
              />
            )}
          />
        )}
        toolbar={(
          <>
            <FilterBar
              search={{
                value: search,
                onChange: setSearch,
                placeholder: 'Search resources…',
              }}
              selects={[
                {
                  id: 'status',
                  label: 'Status',
                  value: statusFilter,
                  onChange: handleStatusChange,
                  options: STATUS_OPTIONS.map((s) => ({ value: s, label: workflowStatusLabel(s) })),
                },
                {
                  id: 'action-type',
                  label: 'Action type',
                  value: actionTypeFilter,
                  onChange: setActionTypeFilter,
                  options: actionTypes.map((t) => ({ value: t, label: actionTypeLabel(t) })),
                },
                {
                  id: 'resource-type',
                  label: 'Resource type',
                  value: resourceTypeFilter,
                  onChange: setResourceTypeFilter,
                  options: resourceTypes.map((t) => ({ value: t, label: t })),
                },
              ]}
              onClear={hasFilters ? clearFilters : undefined}
              resultCount={{
                shown: sortedItems.length,
                total: search ? items.length : (hasFilters ? total : subscriptionTotal),
                label: 'actions',
              }}
            />
            <FilterPresetsBar
              presets={presets}
              onApply={applyPreset}
              onSave={handleSavePreset}
              onDelete={deletePreset}
            />
          </>
        )}
        footer={items.length > 0 ? (
          <ResourceTableFooter
            shownCount={sortedItems.length}
            loadedCount={loadedCount}
            totalCount={hasFilters ? total : subscriptionTotal}
            hasFilters={hasFilters || Boolean(search.trim())}
            hasMore={hasMore}
            onLoadMore={loadMore}
            isLoadingMore={isLoadingMore}
            hint="Click a row to review"
          />
        ) : null}
        className={embedded ? '' : 'optimization-hub-tab-shell--standalone'}
      >

      {(hasFilters || search) && filteredSavings > 0 && (
        <p className="actions-savings-banner">
          Distinct filtered savings: <strong>{formatCurrency(filteredSavings, { currency, decimals: 0 })}/mo</strong>
        </p>
      )}

      {isLoading && !items.length && <LoadingState message="Loading actions…" />}
      {isError && <QueryErrorState error={error} onRetry={refetch} />}
      {indexReady && !items.length && !isLoading && (
        <EmptyState message="No optimization actions yet. Run analysis, then run the decision engine to merge engine and Advisor signals.">
          {isAdmin && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={decideMutation.isPending}
              onClick={() => decideMutation.mutate()}
            >
              Run decision engine
            </button>
          )}
        </EmptyState>
      )}

      {items.length > 0 && sortedItems.length === 0 && (
        <EmptyState message="No actions match your search. Try clearing filters or broadening your search." />
      )}

      {items.length > 0 && (
        <>
          {isAdmin && selected.size > 0 && (
            <BulkActionBar
              count={selected.size}
              onClear={() => setSelected(new Set())}
              actions={[
                { label: 'Approve', onClick: () => bulkMutation.mutate({ status: 'approved', ids: [...selected] }) },
                { label: 'Reject', onClick: () => bulkMutation.mutate({ status: 'rejected', ids: [...selected] }) },
                { label: 'Defer', onClick: () => bulkMutation.mutate({ status: 'deferred', ids: [...selected] }) },
                { label: 'Assign owner', onClick: () => setShowAssignModal(true) },
              ]}
            />
          )}

          <div className="rec-view-toolbar no-print">
            <OptimizationGroupByToggle value={groupBy} onChange={setGroupBy} showFlat />
            {groupBy !== 'flat' && activeGroups.length > 1 && (
              <div className="optimization-actions-group-controls">
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAllGroupsOpen(true)}>
                  Expand all
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAllGroupsOpen(false)}>
                  Collapse all
                </button>
              </div>
            )}
          </div>

          {manyActions && groupBy !== 'flat' && (
            <p className="optimization-actions-hint">
              {sortedItems.length.toLocaleString()} actions — groups start collapsed for faster browsing. Use <strong>Flat list</strong> or search to scan quickly.
            </p>
          )}

          {groupBy === 'resource_type' && (
            <div className="opt-grouped-actions">
              {groupedByType.map((group) => (
                <OptimizationGroupPanel
                  key={group.key}
                  title={group.label}
                  count={groupCountLabel(group)}
                  savings={group.savings}
                  savingsHint="Distinct"
                  currency={currency}
                  open={isGroupOpen(group.key)}
                  onOpenChange={(next) => setGroupOpen(group.key, next)}
                  scrollableBody={group.items.length > 12 && group.items.length < VIRTUAL_SCROLL_THRESHOLD}
                >
                  {renderActionsTable(group.items, group.key)}
                </OptimizationGroupPanel>
              ))}
            </div>
          )}

          {groupBy === 'resource_group' && (
            <div className="opt-grouped-actions">
              {groupedByRg.map((group) => (
                <OptimizationGroupPanel
                  key={group.key}
                  title={group.label}
                  count={groupCountLabel(group)}
                  savings={group.savings}
                  savingsHint="Distinct"
                  currency={currency}
                  open={isGroupOpen(group.key)}
                  onOpenChange={(next) => setGroupOpen(group.key, next)}
                  scrollableBody={group.items.length > 12 && group.items.length < VIRTUAL_SCROLL_THRESHOLD}
                >
                  {renderActionsTable(group.items, group.key)}
                </OptimizationGroupPanel>
              ))}
            </div>
          )}

          {groupBy === 'flat' && renderActionsTable(sortedItems)}
        </>
      )}

      {reviewAction && (
        <ActionApprovalModal
          action={reviewAction}
          currency={currency}
          isAdmin={isAdmin}
          isPending={updateMutation.isPending}
          onClose={closeReview}
          onSubmit={(body) => {
            updateMutation.mutate(
              { actionId: reviewAction.id, body },
              { onSuccess: () => closeReview() },
            );
          }}
        />
      )}

      {showAssignModal && (
        <BulkAssignModal
          count={selected.size}
          isPending={assignMutation.isPending}
          onClose={() => setShowAssignModal(false)}
          onSubmit={(owner) => assignMutation.mutate({ owner, ids: [...selected] })}
        />
      )}
      </OptimizationHubTabShell>
    </div>
  );
}

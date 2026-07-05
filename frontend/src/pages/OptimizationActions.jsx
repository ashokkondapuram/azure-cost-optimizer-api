import React, { useContext, useEffect, useMemo, useState } from 'react';
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
import ArmResourceLink from '../components/ArmResourceLink';
import OptimizationActionChip from '../components/optimization/OptimizationActionChip';
import ConfidenceScore from '../components/optimization/ConfidenceScore';
import ActionDetailDrawer from '../components/optimization/ActionDetailDrawer';
import ActionEvidenceSignals from '../components/optimization/ActionEvidenceSignals';
import ActionApprovalModal from '../components/optimization/ActionApprovalModal';
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
import useOptimizationGroupBy from '../hooks/useOptimizationGroupBy';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import { PAGE_ICONS } from '../config/assetIcons';

const STATUS_OPTIONS = ['proposed', 'approved', 'executed', 'rejected', 'deferred'];
const VIRTUAL_SCROLL_THRESHOLD = 80;

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
  const [detailAction, setDetailAction] = useState(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [sortKey, setSortKey] = useState('estimated_monthly_savings');
  const [sortDir, setSortDir] = useState('desc');
  const [showAssignModal, setShowAssignModal] = useState(false);

  useEffect(() => {
    if (embeddedHub?.actionsStatus) {
      setStatusFilter(embeddedHub.actionsStatus);
    }
  }, [embeddedHub?.actionsStatus]);

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
    totalSavings,
    isLoading,
    isError,
    error,
    refetch,
    indexReady,
  } = useOptimizationActions(subscription, filters);

  const { data: trends } = useQueryWithTimeout({
    queryKey: ['optimization-trends', subscription],
    queryFn: () => fetchOptimizationTrends({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 120_000,
    timeout: 3000,
    allowEmpty: true,
  });

  const subscriptionSummary = useOptimizationActions(subscription, {});

  const actionTypes = useMemo(() => uniqueActionTypes(items), [items]);
  const resourceTypes = useMemo(() => uniqueResourceTypes(items), [items]);

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

  const groupedByType = useMemo(() => groupActionsByResourceType(sortedItems), [sortedItems]);
  const groupedByRg = useMemo(() => groupActionsByResourceGroup(sortedItems), [sortedItems]);

  const handleSort = (key) => {
    const next = toggleSort(sortKey, sortDir, key);
    setSortKey(next.key);
    setSortDir(next.direction);
  };

  const applyPreset = (preset) => {
    const f = preset.filters || {};
    setStatusFilter(f.statusFilter || '');
    setActionTypeFilter(f.actionTypeFilter || '');
    setResourceTypeFilter(f.resourceTypeFilter || '');
    setSearch(f.search || '');
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
      toast.success(`Generated ${data.total_actions || 0} actions`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const updateMutation = useMutation({
    mutationFn: ({ actionId, body }) => updateOptimizationAction(actionId, body, subscription),
    onSuccess: (updated, vars) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-actions'] });
      if (updated?.id) {
        setDetailAction(updated);
      }
      setShowApprovalModal(false);
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

  if (!subscription) return <SubscriptionRequired />;

  const useVirtualScroll = sortedItems.length >= VIRTUAL_SCROLL_THRESHOLD && groupBy === 'flat';
  const workflowSummary = subscriptionSummary.summary || summary;
  const subscriptionTotal = subscriptionSummary.total ?? total;
  const subscriptionSavings = subscriptionSummary.totalSavings ?? totalSavings;
  const hasFilters = Boolean(statusFilter || actionTypeFilter || resourceTypeFilter || search);

  const renderActionsTable = (rows) => (
    <ResponsiveTableWrapper>
      <div className="table-wrap">
        <table className={`data-table actions-table${useVirtualScroll && rows === sortedItems ? ' data-table--virtual-head' : ''}`}>
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
              <th>Resource group</th>
              <SortableTableHeader sortKey="action_type" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                Action
              </SortableTableHeader>
              <SortableTableHeader sortKey="confidence" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                Confidence
              </SortableTableHeader>
              <th>Signals</th>
              <SortableTableHeader sortKey="estimated_monthly_savings" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                Est. savings
              </SortableTableHeader>
              <SortableTableHeader sortKey="workflow_status" activeKey={sortKey} direction={sortDir} onSort={handleSort}>
                Status
              </SortableTableHeader>
              <th>Risk</th>
            </tr>
          </thead>
          {!useVirtualScroll || rows !== sortedItems ? (
            <tbody>
              {rows.map((action) => (
                <tr
                  key={action.id}
                  className={`data-table__row--clickable${detailAction?.id === action.id ? ' data-table__row--selected' : ''}`}
                  onClick={() => setDetailAction(action)}
                >
                  {renderActionCells(action)}
                </tr>
              ))}
            </tbody>
          ) : null}
        </table>
        {useVirtualScroll && rows === sortedItems && (
          <VirtualizedTable
            className={`virtual-table--actions${isAdmin ? '' : ' virtual-table--actions-no-select'}`}
            items={sortedItems}
            rowHeight={56}
            height={Math.min(640, sortedItems.length * 56)}
          >
            {(action) => renderVirtualActionRow(action)}
          </VirtualizedTable>
        )}
      </div>
    </ResponsiveTableWrapper>
  );

  const renderActionCells = (action) => (
    <>
      {isAdmin && (
        <td onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Select ${action.resource_name}`}
            checked={selected.has(action.id)}
            onChange={() => toggleSelect(action.id)}
          />
        </td>
      )}
      <td>
        <div className="cell-stack">
          <strong>{action.resource_name}</strong>
          <span className="text-muted text-sm">{action.resource_type}</span>
          <ArmResourceLink resourceId={action.resource_id} />
        </div>
      </td>
      <td className="text-muted">{resourceGroupLabelForAction(action)}</td>
      <td><OptimizationActionChip actionType={action.action_type} /></td>
      <td><ConfidenceScore confidence={action.confidence} compact /></td>
      <td><ActionEvidenceSignals summary={action.evidence_summary} compact /></td>
      <td>
        {action.estimated_monthly_savings > 0
          ? formatCurrency(action.estimated_monthly_savings, { currency })
          : '—'}
      </td>
      <td><span className={`workflow-pill workflow-pill--${action.workflow_status || 'proposed'}`}>{workflowStatusLabel(action.workflow_status)}</span></td>
      <td>{action.performance_risk || '—'}</td>
    </>
  );

  const renderVirtualActionRow = (action) => (
    <div
      className={`virtual-action-row data-table__row--clickable${detailAction?.id === action.id ? ' data-table__row--selected' : ''}`}
      onClick={() => setDetailAction(action)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          setDetailAction(action);
        }
      }}
    >
      {isAdmin && (
        <div className="virtual-action-row__cell" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Select ${action.resource_name}`}
            checked={selected.has(action.id)}
            onChange={() => toggleSelect(action.id)}
          />
        </div>
      )}
      <div className="virtual-action-row__cell">
        <div className="cell-stack">
          <strong>{action.resource_name}</strong>
          <span className="text-muted text-sm">{action.resource_type}</span>
          <ArmResourceLink resourceId={action.resource_id} />
        </div>
      </div>
      <div className="virtual-action-row__cell text-muted">
        {resourceGroupLabelForAction(action)}
      </div>
      <div className="virtual-action-row__cell">
        <OptimizationActionChip actionType={action.action_type} />
      </div>
      <div className="virtual-action-row__cell">
        <ConfidenceScore confidence={action.confidence} compact />
      </div>
      <div className="virtual-action-row__cell">
        <ActionEvidenceSignals summary={action.evidence_summary} compact />
      </div>
      <div className="virtual-action-row__cell">
        {action.estimated_monthly_savings > 0
          ? formatCurrency(action.estimated_monthly_savings, { currency })
          : '—'}
      </div>
      <div className="virtual-action-row__cell">
        <span className={`workflow-pill workflow-pill--${action.workflow_status || 'proposed'}`}>{workflowStatusLabel(action.workflow_status)}</span>
      </div>
      <div className="virtual-action-row__cell">{action.performance_risk || '—'}</div>
    </div>
  );

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
    <div className={`page optimization-actions-page${embedded ? ' optimization-hub-panel__content' : ''}`}>
      {!embedded && (
        <PageHeader
          title="Optimization actions"
          subtitle="Review and approve synthesized actions from merged engine, Advisor, and metrics signals"
          iconKey={PAGE_ICONS.actions || 'recommendations'}
          actions={decideButton}
        />
      )}

      <PageHero
        variant="optimization-actions-hero"
        eyebrow="Decision engine"
        title="Optimization actions"
        subtitle="Each action combines engine findings, Azure Advisor, and utilization metrics into one recommendation."
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
            sub: 'Subscription-wide',
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
          total: hasFilters ? total : subscriptionTotal,
          label: 'actions',
        }}
      />

      <FilterPresetsBar
        presets={presets}
        onApply={applyPreset}
        onSave={handleSavePreset}
        onDelete={deletePreset}
      />

      {hasFilters && totalSavings > 0 && (
        <p className="actions-savings-banner">
          Filtered savings: <strong>{formatCurrency(totalSavings, { currency, decimals: 0 })}/mo</strong>
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

      {items.length > 0 && (
        <div className={`optimization-actions-layout${detailAction ? ' optimization-actions-layout--open' : ''}`}>
          <div className="optimization-actions-layout__main">
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
          </div>

          {groupBy === 'resource_type' && (
            <div className="opt-grouped-actions">
              {groupedByType.map((group) => (
                <OptimizationGroupPanel
                  key={group.key}
                  title={group.label}
                  count={`${group.items.length} action${group.items.length === 1 ? '' : 's'}`}
                  savings={group.savings}
                  currency={currency}
                >
                  {renderActionsTable(group.items)}
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
                  count={`${group.items.length} action${group.items.length === 1 ? '' : 's'}`}
                  savings={group.savings}
                  currency={currency}
                >
                  {renderActionsTable(group.items)}
                </OptimizationGroupPanel>
              ))}
            </div>
          )}

          {groupBy === 'flat' && renderActionsTable(sortedItems)}
          </div>

          {detailAction && (
            <ActionDetailDrawer
              variant="sidebar"
              action={detailAction}
              currency={currency}
              isAdmin={isAdmin}
              onClose={() => setDetailAction(null)}
              onApproveClick={() => setShowApprovalModal(true)}
            />
          )}
        </div>
      )}

      {detailAction && showApprovalModal && (
        <ActionApprovalModal
          action={detailAction}
          currency={currency}
          isAdmin={isAdmin}
          isPending={updateMutation.isPending}
          onClose={() => setShowApprovalModal(false)}
          onSubmit={(body) => {
            updateMutation.mutate({ actionId: detailAction.id, body });
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
    </div>
  );
}

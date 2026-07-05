/**
 * Generic resource list page with per-resource analysis drawer.
 */
import React, { useContext, useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import FilterBar from '../components/FilterBar';
import FilterPresetsBar from '../components/filtering/FilterPresetsBar';
import SortableTableHeader from '../components/table/SortableTableHeader';
import ResponsiveTableWrapper from '../components/responsive/ResponsiveTableWrapper';
import useFilterPresets from '../hooks/useFilterPresets';
import { sortRows, toggleSort } from '../utils/clientSort';
import {
  matchResourceRow, uniqueResourceGroups, resourceGroupOf,
} from '../utils/filterUtils';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import PrintExportButton from '../components/PrintExportButton';
import AssetIcon from '../components/AssetIcon';
import FetchFromAzureButton from '../components/FetchFromAzureButton';
import AdminOnly from '../components/AdminOnly';
import { Play, Square, PauseCircle, Loader2, Trash2 } from 'lucide-react';
import FindingsBadge from '../components/FindingsBadge';
import InlineFindingBadge from '../components/visual/InlineFindingBadge';
import InlineTriggerBadge from '../components/visual/InlineTriggerBadge';
import InlineCostCell from '../components/visual/InlineCostCell';
import BulkTagModal from '../components/visual/BulkTagModal';
import BulkActionBar from '../components/BulkActionBar';
import { useToast } from '../context/ToastContext';
import { bulkPatchResourceTags } from '../api/azure';
import ResourceInsightDrawer from '../components/ResourceInsightDrawer';
import ResourceListHero from '../components/resources/ResourceListHero';
import useResourceSync from '../hooks/useResourceSync';
import usePaginatedResources from '../hooks/usePaginatedResources';
import useResourceSource from '../hooks/useResourceSource';
import useFindingsIndex from '../hooks/useFindingsIndex';
import useAdvisorIndex from '../hooks/useAdvisorIndex';
import AdvisorTableCell from '../components/advisor/AdvisorTableCell';
import { lookupAdvisorForResource } from '../utils/resourceAdvisorUtils';
import { syncTypesForApiPath, apiPathNeedsProperties } from '../utils/syncScope';
import { getColumnConfig, costColumnLabel } from '../config/resourceColumnConfig';
import useColumnConfig from '../hooks/useColumnConfig';
import useMediaQuery from '../hooks/useMediaQuery';
import ColumnPicker from '../components/ColumnPicker';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import { iconForRow, iconForApiPath } from '../config/assetIcons';
import { inventorySourceLabel, resourceLoadingMessage } from '../utils/viewerUi';
import { toDisplayText } from '../utils/formatDisplay';
import { formatCurrency, formatDate } from '../utils/format';
import { resourceTotalCost } from '../utils/costCurrency';
import { enrichVnetRow, vnetDisplaySku } from '../utils/vnetNormalize';
import { enrichPrivateEndpointRow, privateEndpointDisplayConnection } from '../utils/privateEndpointNormalize';
import { enrichPrivateLinkServiceRow, privateLinkServiceDisplaySummary } from '../utils/privateLinkServiceNormalize';
import { enrichPrivateDnsRow, privateDnsDisplaySummary } from '../utils/privateDnsNormalize';
import {
  enrichAppServicePlanRow,
  enrichAppServiceWebappRow,
  appServicePlanDisplaySku,
  appServiceWebappDisplaySku,
} from '../utils/appServiceNormalize';
import { resolveResourceSku } from '../utils/resourceSkuUtils';
import {
  resolveResourceFindings,
  resourceHasFindings,
  countOpenFindings,
  countResourcesWithFindings,
  sumResolvedSavingsForRows,
} from '../utils/resourceFindingsUtils';
import { fetchBilledResourceProperties } from '../api/azure';

function rowValue(row, col) {
  if (col.key === 'findings') return null;
  if (col.prop) {
    const props = row.properties || {};
    return props[col.prop];
  }
  const val = row[col.key] ?? (col.alt ? row[col.alt] : undefined);
  return val;
}

function resourceId(row) {
  return (row.id || row.resource_id || '').toLowerCase();
}

function EmptyCell() {
  return <span className="resource-table__empty">—</span>;
}

function isSortableColumn(col) {
  if (col.type === 'advisor' || col.type === 'findings' || col.type === 'triggers') return false;
  return col.type === 'cost' || col.type === 'state' || col.type === 'date'
    || ['name', 'resource_name', 'location', 'resource_group', 'sku', 'state'].includes(col.key);
}

function buildSortAccessors() {
  return {
    name: (row) => toDisplayText(row.name || row.resource_name || ''),
    resource_name: (row) => toDisplayText(row.resource_name || row.name || ''),
    location: (row) => row.location || '',
    resource_group: (row) => resourceGroupOf(row),
    sku: (row) => toDisplayText(resolveResourceSku(row)),
    state: (row) => toDisplayText(row.state || row.properties?.provisioningState || ''),
    monthlyCost: (row) => resourceTotalCost(row),
    cost: (row) => resourceTotalCost(row),
  };
}

const STATE_ICONS = {
  running: Play,
  active: Play,
  stopped: Square,
  deallocated: PauseCircle,
  creating: Loader2,
  deleting: Trash2,
};

function StateBadge({ stateText, status }) {
  const lower = String(stateText || '').toLowerCase();
  const key = Object.keys(STATE_ICONS).find((k) => lower.includes(k)) || null;
  const Icon = key ? STATE_ICONS[key] : null;
  const isMissing = status === 'missing' || /doesn't exist on azure/i.test(stateText);
  const isUnknown = status === 'unknown' || stateText === '—';
  return (
    <span className={`badge resource-state-badge ${
      isMissing ? 'badge-critical'
        : isUnknown ? 'badge-medium'
        : /running|active|enabled|succeeded|attached/i.test(stateText) ? 'badge-low'
        : /stopped|deallocated|disabled|unattached|unassociated/i.test(stateText) ? 'badge-critical'
        : 'badge-medium'
    }`}>
      {Icon && <Icon size={11} className={key === 'creating' ? 'spin' : ''} aria-hidden />}
      {stateText}
    </span>
  );
}

export default function ResourceList({ title, apiPath, iconSrc, iconKey }) {
  const { subscription, billingCurrency, subscriptionOptions } = useContext(AppCtx);
  const queryClient = useQueryClient();
  const toast = useToast();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get('search') || '');
  const [rgFilter, setRgFilter] = useState('');
  const [findingsOnly, setFindingsOnly] = useState(false);
  const [costOnly, setCostOnly] = useState(false);
  const [sortKey, setSortKey] = useState('name');
  const [sortDir, setSortDir] = useState('asc');
  const [selected, setSelected] = useState(null);
  const [bulkSelected, setBulkSelected] = useState(new Set());
  const [showBulkTagModal, setShowBulkTagModal] = useState(false);
  const [bulkTagPending, setBulkTagPending] = useState(false);
  const [hydratingId, setHydratingId] = useState(null);
  const { dataSource, isLive, resetToDatabase, isAdmin } = useResourceSource();
  const pageIcon = iconKey || iconSrc || iconForApiPath(apiPath) || 'default';
  const currency = billingCurrency || 'CAD';
  const subLabel = subscriptionOptions.find((s) => s.subscriptionId === subscription)?.displayName;
  const columnConfig = getColumnConfig(apiPath);
  const baseColumns = (columnConfig?.columns || []).map((col) => (
    col.type === 'cost' ? { ...col, label: costColumnLabel(currency) } : col
  ));
  const {
    visibleColumns,
    config,
    toggleColumn,
    moveColumn,
    restoreDefaults,
    allColumns,
  } = useColumnConfig(apiPath, baseColumns);
  const cols = visibleColumns;
  const isMobile = useMediaQuery('(max-width: 767px)');

  const filterState = useMemo(() => ({
    search,
    rgFilter,
    findingsOnly,
    costOnly,
  }), [search, rgFilter, findingsOnly, costOnly]);

  const { presets, savePreset, deletePreset } = useFilterPresets(`resources:${apiPath}`, filterState);

  const sortAccessors = useMemo(() => buildSortAccessors(), []);

  useEffect(() => {
    setBulkSelected(new Set());
  }, [apiPath, subscription, search, rgFilter, findingsOnly, costOnly]);

  const toggleBulkSelect = (rowId) => {
    setBulkSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  };

  const toggleBulkSelectAll = () => {
    if (bulkSelected.size === sortedRows.length) {
      setBulkSelected(new Set());
      return;
    }
    setBulkSelected(new Set(sortedRows.map((row) => resourceId(row))));
  };

  const handleBulkAddTag = () => {
    setShowBulkTagModal(true);
  };

  const submitBulkTag = async (tags) => {
    setBulkTagPending(true);
    try {
      const result = await bulkPatchResourceTags({
        subscription_id: subscription,
        resource_ids: [...bulkSelected],
        tags,
      });
      toast.success(`Updated tags on ${result.updated || 0} resources`);
      setBulkSelected(new Set());
      setShowBulkTagModal(false);
      queryClient.invalidateQueries({ predicate: (q) => Array.isArray(q.queryKey) && q.queryKey[0] === apiPath });
    } catch (err) {
      toast.error('Could not update tags');
    } finally {
      setBulkTagPending(false);
    }
  };

  useEffect(() => {
    const q = searchParams.get('search');
    if (q != null) setSearch(q);
  }, [searchParams]);

  const { byResourceId, savingsByResource, truncated, indexReady } = useFindingsIndex(subscription);
  const {
    byResourceId: advisorByResourceId,
    indexReady: advisorIndexReady,
    isLoading: advisorIndexLoading,
    isError: advisorIndexError,
  } = useAdvisorIndex(subscription);

  const {
    items: data,
    total: dataTotal,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
    hasMore,
    loadMore,
    isLoadingMore,
  } = usePaginatedResources({
    apiPath,
    subscription,
    dataSource,
    enabled: !!subscription,
    includeProperties: apiPathNeedsProperties(apiPath),
  });

  const isVnetPage = apiPath === '/resources/vnets';
  const isPrivateEndpointPage = apiPath === '/resources/privateendpoints';
  const isPrivateLinkServicePage = apiPath === '/resources/privatelinkservices';
  const isPrivateDnsPage = apiPath === '/resources/privatedns';
  const isAppServicePage = apiPath === '/resources/appservices';
  const isAppServicePlanPage = apiPath === '/resources/appserviceplans';
  const displayRows = useMemo(() => {
    const base = data || [];
    if (isVnetPage) return base.map(enrichVnetRow);
    if (isPrivateEndpointPage) return base.map(enrichPrivateEndpointRow);
    if (isPrivateLinkServicePage) return base.map(enrichPrivateLinkServiceRow);
    if (isPrivateDnsPage) return base.map(enrichPrivateDnsRow);
    if (isAppServicePage) return base.map(enrichAppServiceWebappRow);
    if (isAppServicePlanPage) return base.map(enrichAppServicePlanRow);
    return base;
  }, [
    data,
    isVnetPage,
    isPrivateEndpointPage,
    isPrivateLinkServicePage,
    isPrivateDnsPage,
    isAppServicePage,
    isAppServicePlanPage,
  ]);

  const isBilledResourcesPage = apiPath === '/resources/from-cost';

  const handleSelectRow = async (row) => {
    setSelected(row);
    const rid = resourceId(row);
    if (!isBilledResourcesPage || !subscription || !rid) return;
    if (row.inInventory) return;
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

  const syncTypes = syncTypesForApiPath(apiPath);

  const { sync, syncing } = useResourceSync({
    subscription,
    syncTypes,
    includeCosts: false,
    invalidateKeys: [[apiPath, subscription], ['resource-counts', subscription], ['findings-index', subscription], ['advisor-index', subscription]],
  });

  const handleSync = async () => {
    try {
      resetToDatabase();
      await sync();
      await refetch();
    } catch {
      /* syncMsg */
    }
  };

  const handleRefresh = () => {
    resetToDatabase();
    refetch();
    queryClient.invalidateQueries({ queryKey: ['findings-index', subscription] });
    queryClient.invalidateQueries({ queryKey: ['advisor-index', subscription] });
  };

  const rows = displayRows.filter((r) => {
    if (!matchResourceRow(r, search, [
      (row) => toDisplayText(row.sku),
      (row) => toDisplayText(row.state),
    ])) return false;
    if (rgFilter && resourceGroupOf(r) !== rgFilter) return false;
    const rid = resourceId(r);
    if (findingsOnly && !resourceHasFindings(r, byResourceId.get(rid) || [], { indexReady })) return false;
    if (costOnly && resourceTotalCost(r) <= 0) return false;
    return true;
  });

  const sortedRows = useMemo(
    () => sortRows(rows, sortKey, sortDir, sortAccessors),
    [rows, sortKey, sortDir, sortAccessors],
  );

  const handleSort = (key) => {
    const next = toggleSort(sortKey, sortDir, key);
    setSortKey(next.key);
    setSortDir(next.direction);
  };

  const applyPreset = (preset) => {
    const f = preset.filters || {};
    setSearch(f.search || '');
    setRgFilter(f.rgFilter || '');
    setFindingsOnly(!!f.findingsOnly);
    setCostOnly(!!f.costOnly);
  };

  const handleSavePreset = () => {
    const name = window.prompt('Preset name');
    if (name) savePreset(name);
  };

  const resourceGroups = uniqueResourceGroups(data || []);
  const hasFilters = !!(search || rgFilter || findingsOnly || costOnly);

  const findingsOptions = { indexReady };
  const resourcesWithFindings = countResourcesWithFindings(rows, byResourceId, resourceId, findingsOptions);
  const openFindings = countOpenFindings(rows, byResourceId, resourceId, findingsOptions);
  const totalSavings = sumResolvedSavingsForRows(rows, byResourceId, savingsByResource, resourceId, findingsOptions);

  const groupedRows = useMemo(() => {
    const groups = new Map();
    for (const r of sortedRows) {
      const rg = r.resourceGroup || r.resource_group || '—';
      if (!groups.has(rg)) groups.set(rg, []);
      groups.get(rg).push(r);
    }
    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [sortedRows]);

  const renderCell = (row, col) => {
    if (col.type === 'advisor') {
      const recommendations = lookupAdvisorForResource(advisorByResourceId, row);
      return (
        <AdvisorTableCell
          recommendations={recommendations}
          indexReady={advisorIndexReady && !advisorIndexLoading}
          isError={advisorIndexError}
          currency={currency}
          subscriptionHasAdvisor={advisorByResourceId.size > 0}
        />
      );
    }

    if (col.type === 'triggers') {
      const rid = resourceId(row);
      const indexFindings = byResourceId.get(rid) || [];
      return (
        <InlineTriggerBadge
          findings={indexFindings}
          indexReady={indexReady}
        />
      );
    }

    if (col.type === 'findings') {
      const rid = resourceId(row);
      const indexFindings = byResourceId.get(rid) || [];
      return (
        <InlineFindingBadge
          resource={row}
          indexFindings={indexFindings}
          savings={savingsByResource.get(rid) || 0}
          currency={currency}
          indexReady={indexReady}
        />
      );
    }

    if (col.type === 'cost') {
      const cost = resourceTotalCost(row);
      if (cost > 0) {
        return <InlineCostCell amount={cost} row={row} currency={currency} />;
      }
      if (row.costPending) {
        return <span className="resource-cost resource-cost--pending">Pending</span>;
      }
      if (row.type === 'network/vnet' || isVnetPage) {
        return (
          <span className="resource-cost resource-cost--free" title="Base VNet has no charge; peering and egress may bill separately">
            {formatCurrency(0, { currency })}
          </span>
        );
      }
      if (
        row.type === 'network/privateendpoint'
        || row.type === 'network/privatelinkservice'
        || row.type === 'network/privatedns'
        || isPrivateEndpointPage
        || isPrivateLinkServicePage
        || isPrivateDnsPage
      ) {
        return (
          <span
            className="resource-cost resource-cost--free"
            title="No total cost recorded; Private Link and DNS zones may bill when in use"
          >
            {formatCurrency(0, { currency })}
          </span>
        );
      }
      return <EmptyCell />;
    }

    if (col.type === 'vnet_address') {
      const text = vnetDisplaySku(row);
      return text && text !== '—' ? (
        <span className="resource-vnet-cidr" style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{text}</span>
      ) : <EmptyCell />;
    }

    if (col.type === 'subnet_count') {
      const count = row.subnetCount ?? (row.properties?.subnets || []).length;
      return count > 0 ? count.toLocaleString() : <EmptyCell />;
    }

    if (col.type === 'pe_connection') {
      const text = privateEndpointDisplayConnection(row);
      return text && text !== '—' ? (
        <span className="resource-pe-connection">{text}</span>
      ) : <EmptyCell />;
    }

    if (col.type === 'pls_summary') {
      const text = privateLinkServiceDisplaySummary(row);
      return text && text !== '—' ? (
        <span className="resource-pls-summary">{text}</span>
      ) : <EmptyCell />;
    }

    if (col.type === 'private_dns_summary') {
      const text = privateDnsDisplaySummary(row);
      return text && text !== '—' ? (
        <span className="resource-private-dns-summary">{text}</span>
      ) : <EmptyCell />;
    }

    if (col.type === 'app_service_sku') {
      const text = appServiceWebappDisplaySku(row);
      return text && text !== '—' ? (
        <span className="resource-app-service-sku">{text}</span>
      ) : <EmptyCell />;
    }

    if (col.type === 'app_service_plan_sku') {
      const text = appServicePlanDisplaySku(row);
      return text && text !== '—' ? (
        <span className="resource-app-service-plan-sku">{text}</span>
      ) : <EmptyCell />;
    }

    if (col.key === 'sku') {
      const sku = resolveResourceSku(row);
      if (sku) {
        return <span className="resource-sku">{toDisplayText(sku)}</span>;
      }
      return <EmptyCell />;
    }

    if (col.key === 'name' || col.key === 'resource_name') {
      const label = toDisplayText(rowValue(row, col));
      return (
        <span className="resource-table__name-cell">
          <AssetIcon iconKey={iconForRow(row, { apiPath, fallback: pageIcon })} size={18} />
          <span className="resource-name">{label}</span>
        </span>
      );
    }

    if (col.type === 'state') {
      const status = row.azureStatus;
      const stateText = toDisplayText(rowValue(row, col));
      return <StateBadge stateText={stateText} status={status} />;
    }

    if (col.type === 'date') {
      const val = rowValue(row, col);
      return val ? formatDate(val) : <EmptyCell />;
    }

    const val = rowValue(row, col);
    if (val == null) return <EmptyCell />;
    if (typeof val === 'number') return val.toLocaleString();
    if (typeof val === 'boolean') return val ? 'Yes' : 'No';
    const text = toDisplayText(val);
    if (text.length > 60) return `${text.slice(0, 58)}…`;
    return text;
  };

  const selectedFindings = selected
    ? resolveResourceFindings(selected, byResourceId.get(resourceId(selected)) || [], { indexReady })
    : [];

  const sourceLabel = inventorySourceLabel({ isAdmin, isLive });

  return (
    <div className="page-shell resource-list-page">
      <PageHeader title={title} iconKey={pageIcon}>
        <div className="page-header-actions__row">
          <AdminOnly>
            <FetchFromAzureButton
              onClick={handleSync}
              loading={syncing}
              disabled={!subscription || syncTypes.length === 0}
            />
          </AdminOnly>
          <button type="button" className="btn btn-secondary btn-sm" onClick={handleRefresh} disabled={isFetching || !subscription}>
            <RefreshCw size={13} className={isFetching ? 'spin' : ''} /> Refresh
          </button>
          <ColumnPicker
            columns={allColumns}
            visibleKeys={config.visible || []}
            onToggle={toggleColumn}
            onMove={moveColumn}
            onRestore={restoreDefaults}
          />
        </div>
      </PageHeader>

      {!subscription && <SubscriptionRequired />}

      {subscription && (
        <div className="resource-list-layout">
          <ResourceListHero
            title={title}
            subscriptionLabel={subLabel}
            filteredCount={rows.length}
            totalCount={dataTotal}
            sourceLabel={sourceLabel}
            resourcesWithFindings={resourcesWithFindings}
            openFindings={openFindings}
            totalSavings={totalSavings}
            currency={currency}
            isLive={isLive}
            isLoading={isLoading}
          />

          {truncated && resourcesWithFindings > 0 && (
            <div className="rec-truncation-banner" role="status">
              Findings index capped at 2,000 — some badges may be incomplete until you narrow the list.
            </div>
          )}

          <section className="rec-filter-panel card">
            <FilterBar
              className="rec-filter-bar"
              search={{
                value: search,
                onChange: setSearch,
                placeholder: 'Search name, group, location…',
              }}
              selects={resourceGroups.length > 0 ? [{
                id: 'rg',
                label: 'Resource group',
                value: rgFilter,
                onChange: setRgFilter,
                options: [
                  { value: '', label: 'All resource groups' },
                  ...resourceGroups.map((rg) => ({ value: rg, label: rg })),
                ],
              }] : []}
              toggles={[
                { id: 'findings', label: 'With open findings', checked: findingsOnly, onChange: setFindingsOnly },
                { id: 'cost', label: 'With total cost', checked: costOnly, onChange: setCostOnly },
              ]}
              onClear={hasFilters ? () => {
                setSearch('');
                setRgFilter('');
                setFindingsOnly(false);
                setCostOnly(false);
              } : undefined}
            />
            <FilterPresetsBar
              presets={presets}
              onApply={applyPreset}
              onSave={handleSavePreset}
              onDelete={deletePreset}
            />
          </section>

          {isLoading && (
            <LoadingState message={resourceLoadingMessage(isAdmin, { isLive, label: title.toLowerCase() })} />
          )}
          {isError && <QueryErrorState error={error} onRetry={refetch} />}

          {!isLoading && !isError && rows.length === 0 && (
            <EmptyState
              iconKey={pageIcon}
              message={
                hasFilters
                  ? 'No results match your filters.'
                  : isAdmin
                    ? 'No data in the database. Fetch from Azure to load and save inventory.'
                    : 'No data available yet. Ask an administrator to sync inventory from Azure.'
              }
            >
              {!hasFilters && (
                <AdminOnly>
                  <div className="resource-list-empty-actions">
                    <FetchFromAzureButton onClick={handleSync} loading={syncing} disabled={!subscription} className="btn btn-primary" />
                  </div>
                </AdminOnly>
              )}
            </EmptyState>
          )}

          {!isLoading && !isError && rows.length > 0 && isMobile && (
            <div className="resource-card-list">
              {groupedRows.map(([rg, groupRows]) => (
                <section key={rg} className="resource-card-group">
                  <header className="resource-card-group__header">
                    <span>{rg}</span>
                    <span className="resource-card-group__count">{groupRows.length}</span>
                  </header>
                  {groupRows.map((row) => {
                    const rid = resourceId(row);
                    const nameCol = cols.find((c) => c.key === 'name' || c.key === 'resource_name') || cols[0];
                    const stateCol = cols.find((c) => c.type === 'state');
                    const costCol = cols.find((c) => c.type === 'cost');
                    const stateText = stateCol ? toDisplayText(rowValue(row, stateCol)) : '';
                    return (
                      <button
                        type="button"
                        key={row.id || row.resource_id || `${row.name}-${row.location}`}
                        className="resource-card"
                        onClick={() => handleSelectRow(row)}
                      >
                        <div className="resource-card__head">
                          <AssetIcon iconKey={iconForRow(row, { apiPath, fallback: pageIcon })} size={20} />
                          <div className="resource-card__title">
                            <span className="resource-card__name">{toDisplayText(rowValue(row, nameCol))}</span>
                            {stateCol && stateText && (
                              <StateBadge stateText={stateText} status={row.azureStatus} />
                            )}
                          </div>
                        </div>
                        <div className="resource-card__meta">
                          {costCol && (
                            <span className="resource-card__cost">
                              {resourceTotalCost(row) > 0
                                ? formatCurrency(resourceTotalCost(row), { currency })
                                : '—'}
                            </span>
                          )}
                          <FindingsBadge
                            resource={row}
                            indexFindings={byResourceId.get(rid) || []}
                            savings={savingsByResource.get(rid) || 0}
                            currency={currency}
                            indexReady={indexReady}
                          />
                          <AdvisorTableCell
                            recommendations={advisorByResourceId.get(rid) || []}
                            indexReady={advisorIndexReady && !advisorIndexLoading}
                            isError={advisorIndexError}
                            currency="USD"
                          />
                        </div>
                      </button>
                    );
                  })}
                </section>
              ))}
              <footer className="resource-table-footer">
                <span>
                  {rows.length.toLocaleString()} of {dataTotal.toLocaleString()} records
                  {hasFilters ? ' (filtered)' : ''}
                </span>
                {hasMore && !hasFilters && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => loadMore()}
                    disabled={isLoadingMore}
                  >
                    {isLoadingMore ? 'Loading…' : 'Load more'}
                  </button>
                )}
              </footer>
            </div>
          )}

          {isAdmin && bulkSelected.size > 0 && (
            <BulkActionBar
              count={bulkSelected.size}
              onClear={() => setBulkSelected(new Set())}
              actions={[
                { label: 'Add tag', onClick: handleBulkAddTag, variant: 'primary' },
              ]}
            />
          )}

          {!isLoading && !isError && rows.length > 0 && !isMobile && (
            <div className="card resource-table-card">
              <ResponsiveTableWrapper className="resource-table-wrap">
                <table className="table resource-table">
                  <thead>
                    <tr>
                      {isAdmin && (
                        <th className="resource-table__select-col">
                          <input
                            type="checkbox"
                            aria-label="Select all visible resources"
                            checked={bulkSelected.size === sortedRows.length && sortedRows.length > 0}
                            onChange={toggleBulkSelectAll}
                          />
                        </th>
                      )}
                      {cols.map((col) => (
                        isSortableColumn(col) ? (
                          <SortableTableHeader
                            key={col.key}
                            sortKey={col.key}
                            activeKey={sortKey}
                            direction={sortDir}
                            onSort={handleSort}
                          >
                            {col.label}
                          </SortableTableHeader>
                        ) : (
                          <th key={col.key}>{col.label}</th>
                        )
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {groupedRows.map(([rg, groupRows]) => (
                      <React.Fragment key={rg}>
                        <tr className="resource-group-header">
                          <td colSpan={cols.length + (isAdmin ? 1 : 0)}>
                            <span className="resource-group-header__label">{rg}</span>
                            <span className="resource-group-header__count">{groupRows.length}</span>
                          </td>
                        </tr>
                        {groupRows.map((row) => {
                          const rid = resourceId(row);
                          const isSelected = selected && resourceId(selected) === rid;
                          const nameCol = cols.find((c) => c.key === 'name' || c.key === 'resource_name') || cols[0];
                          const rowLabel = toDisplayText(rowValue(row, nameCol)) || 'resource';
                          return (
                          <tr
                            key={row.id || row.resource_id || `${row.name}-${row.location}`}
                            className={`resource-table__row${isSelected ? ' resource-row--selected' : ''}`}
                            tabIndex={0}
                            role="button"
                            aria-label={`View details for ${rowLabel}`}
                            onClick={() => handleSelectRow(row)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                handleSelectRow(row);
                              }
                            }}
                          >
                            {isAdmin && (
                              <td className="resource-table__select-col" onClick={(e) => e.stopPropagation()}>
                                <input
                                  type="checkbox"
                                  aria-label={`Select ${rowLabel}`}
                                  checked={bulkSelected.has(rid)}
                                  onChange={() => toggleBulkSelect(rid)}
                                />
                              </td>
                            )}
                            {cols.map((col) => (
                              <td key={col.key}>{renderCell(row, col)}</td>
                            ))}
                          </tr>
                          );
                        })}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </ResponsiveTableWrapper>
              <footer className="resource-table-footer">
                <span>
                  {rows.length.toLocaleString()} of {dataTotal.toLocaleString()} records
                  {hasFilters ? ' (filtered)' : ''}
                  · Click a row for details
                  {hydratingId ? ' · Loading Azure properties…' : ''}
                </span>
                {hasMore && !hasFilters && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => loadMore()}
                    disabled={isLoadingMore}
                  >
                    {isLoadingMore ? 'Loading…' : 'Load more'}
                  </button>
                )}
              </footer>
            </div>
          )}
        </div>
      )}

      <ResourceInsightDrawer
        resource={selected}
        findings={selectedFindings}
        onClose={() => setSelected(null)}
        title={title}
        iconKey={pageIcon}
        apiPath={apiPath}
        currency={currency}
        indexReady={indexReady}
      />

      {showBulkTagModal && (
        <BulkTagModal
          count={bulkSelected.size}
          isPending={bulkTagPending}
          onClose={() => setShowBulkTagModal(false)}
          onSubmit={submitBulkTag}
        />
      )}
    </div>
  );
}

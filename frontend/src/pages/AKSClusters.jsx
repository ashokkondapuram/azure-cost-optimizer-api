import React, { useContext, useMemo, useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import PageHeader from '../components/PageHeader';
import AssetIcon from '../components/AssetIcon';
import FilterBar from '../components/FilterBar';
import FetchFromAzureButton from '../components/FetchFromAzureButton';
import AdminOnly from '../components/AdminOnly';
import useResourceSync from '../hooks/useResourceSync';
import usePaginatedResources from '../hooks/usePaginatedResources';
import useResourceSource from '../hooks/useResourceSource';
import { PAGE_ICONS } from '../config/assetIcons';
import { AppCtx } from '../App';
import { syncTypesForApiPath } from '../utils/syncScope';
import InlineFindingBadge from '../components/visual/InlineFindingBadge';
import InlineCostCell from '../components/visual/InlineCostCell';
import ResourceInsightDrawer from '../components/ResourceInsightDrawer';
import useFindingsIndex from '../hooks/useFindingsIndex';
import useAdvisorIndex from '../hooks/useAdvisorIndex';
import AdvisorTableCell from '../components/advisor/AdvisorTableCell';
import InlineTriggerBadge from '../components/visual/InlineTriggerBadge';
import { lookupAdvisorForResource } from '../utils/resourceAdvisorUtils';
import { resourceTotalCost } from '../utils/costCurrency';
import { costColumnLabel } from '../config/resourceColumnConfig';
import ResourceInventoryShell from '../components/ResourceInventoryShell';
import ResourceInventoryPageShell from '../components/resources/ResourceInventoryPageShell';
import { FINDINGS_INDEX_LIMIT } from '../hooks/useFindingsIndex';
import { QueryErrorState, SubscriptionRequired, LoadingState, EmptyState } from '../components/QueryStates';
import ResourceTableFooter from '../components/table/ResourceTableFooter';
import useInventoryInspectDeepLink from '../hooks/useInventoryInspectDeepLink';
import { resourceTableWrapClass } from '../utils/resourceTableLayout';
import { inventoryListSubtitle } from '../utils/viewerUi';
import { dedupeAksClusters, normalizeAksCluster } from '../it-services/containers-aks';
import {
  matchResourceRow, uniqueResourceGroups, resourceGroupOf,
} from '../utils/filterUtils';
import {
  resolveResourceFindings, resourceHasFindings,
} from '../utils/resourceFindingsUtils';

const STATE_COLOR = { Running: 'var(--success)', Stopped: 'var(--warning)', Failed: 'var(--danger)', Creating: 'var(--accent)', Succeeded: 'var(--success)' };

export default function AKSClusters() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get('search') || '');
  const [rgFilter, setRgFilter] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [versionFilter, setVersionFilter] = useState('');
  const [findingsOnly, setFindingsOnly] = useState(false);
  const [selected, setSelected] = useState(null);
  const [drawerFocus, setDrawerFocus] = useState(null);
  const currency = billingCurrency || 'CAD';
  const { byResourceId, savingsByResource, truncated, indexReady, isError: findingsIndexError, error: findingsIndexErr } = useFindingsIndex(subscription);
  const {
    byResourceId: advisorByResourceId,
    indexReady: advisorIndexReady,
    isLoading: advisorIndexLoading,
    isError: advisorIndexError,
  } = useAdvisorIndex(subscription);
  const { dataSource, isLive, resetToDatabase, isAdmin } = useResourceSource();

  const { sync, syncing } = useResourceSync({
    subscription,
    syncTypes: syncTypesForApiPath('/resources/aks'),
    includeCosts: false,
    invalidateKeys: [['/resources/aks', subscription], ['resource-counts', subscription], ['findings-index', subscription]],
  });

  const {
    items: clusters,
    total: clustersTotal,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
    hasMore,
    loadMore,
    isLoadingMore,
  } = usePaginatedResources({
    apiPath: '/resources/aks',
    subscription,
    dataSource,
    enabled: !!subscription,
    includeProperties: true,
  });

  const normalizedClusters = useMemo(
    () => dedupeAksClusters(clusters).map(normalizeAksCluster),
    [clusters],
  );

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
  };

  const rid = (c) => (c.id || '').toLowerCase();

  useEffect(() => {
    const q = searchParams.get('search');
    if (q != null) setSearch(q);
  }, [searchParams]);

  const handleInspectOpen = useCallback((cluster, section) => {
    setSelected(cluster);
    setDrawerFocus(section || 'advanced-analysis');
  }, []);

  useInventoryInspectDeepLink({
    items: normalizedClusters,
    isLoading,
    isLoadingMore,
    getResourceId: rid,
    hasMore,
    loadMore,
    onOpen: handleInspectOpen,
    enabled: !!subscription,
  });

  const filtered = normalizedClusters.filter((c) => {
    if (!matchResourceRow(c, search, [
      (row) => row._version,
      (row) => row._state,
      (row) => String(row._nodeCount),
    ])) return false;
    if (rgFilter && resourceGroupOf(c) !== rgFilter) return false;
    if (stateFilter && c._state !== stateFilter) return false;
    if (versionFilter && c._version !== versionFilter) return false;
    if (findingsOnly && !resourceHasFindings(c, byResourceId.get(rid(c)) || [], { indexReady })) return false;
    return true;
  });

  const resourceGroups = uniqueResourceGroups(normalizedClusters);
  const stateOptions = useMemo(
    () => [...new Set(normalizedClusters.map((c) => c._state).filter(Boolean))].sort(),
    [normalizedClusters],
  );
  const versionOptions = useMemo(
    () => [...new Set(normalizedClusters.map((c) => c._version).filter((v) => v && v !== '—'))].sort(),
    [normalizedClusters],
  );
  const hasFilters = !!(search || rgFilter || stateFilter || versionFilter || findingsOnly);

  const running = normalizedClusters.filter((c) => c._state === 'Running' || c._state === 'Succeeded').length;
  const stopped = normalizedClusters.filter((c) => c._state === 'Stopped').length;
  const totalNodes = normalizedClusters.reduce((sum, c) => sum + c._nodeCount, 0);
  const versions = versionOptions;

  const selectedCluster = selected ? normalizeAksCluster(selected) : null;
  const selectedFindings = selectedCluster
    ? resolveResourceFindings(selectedCluster, byResourceId.get((selectedCluster.id || '').toLowerCase()) || [], { indexReady })
    : [];
  const totalCost = (c) => resourceTotalCost(c);

  const groupedClusters = (() => {
    const groups = new Map();
    for (const c of filtered) {
      const rg = c.resourceGroup || c.resource_group || '—';
      if (!groups.has(rg)) groups.set(rg, []);
      groups.get(rg).push(c);
    }
    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  })();

  return (
    <div className="page-shell resource-inventory-page--shell">
      <PageHeader
        title="AKS clusters"
        iconSrc={PAGE_ICONS.aks}
        subtitle={subscription
          ? inventoryListSubtitle({
            isAdmin,
            isLive,
            suffix: `${filtered.length} of ${clustersTotal} clusters`,
          })
          : 'Select a subscription'}
      >
        <AdminOnly>
          <FetchFromAzureButton onClick={handleSync} loading={syncing} disabled={!subscription} />
        </AdminOnly>
        <button type="button" className="btn btn-secondary" onClick={handleRefresh} disabled={!subscription || isFetching}>
          <RefreshCw size={13} className={isFetching ? 'spin' : ''} /> Refresh
        </button>
      </PageHeader>

      {subscription && !isError && (
        <ResourceInventoryPageShell
          hero={(
            <>
              {findingsIndexError && (
                <div className="alert alert--warning" role="status" style={{ marginBottom: '1rem' }}>
                  Open findings are temporarily unavailable. Cluster inventory still loads.
                </div>
              )}
              <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
                <div className="stat-card accent">
                  <AssetIcon src={PAGE_ICONS.aks} size={22} className="stat-card__icon" alt="" />
                  <div className="stat-label">Total clusters</div><div className="stat-value">{clustersTotal}</div><div className="stat-sub">{running} running</div>
                </div>
                <div className="stat-card warning">
                  <AssetIcon src={PAGE_ICONS.kubernetes} size={22} className="stat-card__icon" alt="" />
                  <div className="stat-label">Stopped</div><div className="stat-value">{stopped}</div><div className="stat-sub">Not incurring compute</div>
                </div>
                <div className="stat-card success">
                  <AssetIcon src={PAGE_ICONS.k8sNode} size={22} className="stat-card__icon" alt="" />
                  <div className="stat-label">Total nodes</div><div className="stat-value">{totalNodes.toLocaleString()}</div><div className="stat-sub">Across all pools</div>
                </div>
                <div className="stat-card purple">
                  <AssetIcon src={PAGE_ICONS.nodepool} size={22} className="stat-card__icon" alt="" />
                  <div className="stat-label">K8s versions</div><div className="stat-value">{versions.length}</div><div className="stat-sub">{versions[0] || '—'} (latest in use)</div>
                </div>
              </div>
              {filtered.length > 0 && (
                <ResourceInventoryShell
                  showFindingsSummary
                  summaryRows={filtered}
                  byResourceId={byResourceId}
                  savingsByResource={savingsByResource}
                  currency={currency}
                  isAdmin={isAdmin}
                  getResourceId={rid}
                  truncated={truncated}
                  indexReady={indexReady}
                  findingsLimit={FINDINGS_INDEX_LIMIT}
                  emptyUserMessage="No open findings for AKS clusters"
                />
              )}
            </>
          )}
          toolbar={(
            <FilterBar
              search={{
                value: search,
                onChange: setSearch,
                placeholder: 'Search name, version, location…',
              }}
              selects={[
                ...(resourceGroups.length > 0 ? [{
                  id: 'rg',
                  label: 'Resource group',
                  value: rgFilter,
                  onChange: setRgFilter,
                  options: [
                    { value: '', label: 'All resource groups' },
                    ...resourceGroups.map((rg) => ({ value: rg, label: rg })),
                  ],
                }] : []),
                ...(stateOptions.length > 0 ? [{
                  id: 'state',
                  label: 'State',
                  value: stateFilter,
                  onChange: setStateFilter,
                  options: [
                    { value: '', label: 'All states' },
                    ...stateOptions.map((s) => ({ value: s, label: s })),
                  ],
                }] : []),
                ...(versionOptions.length > 0 ? [{
                  id: 'version',
                  label: 'K8s version',
                  value: versionFilter,
                  onChange: setVersionFilter,
                  options: [
                    { value: '', label: 'All versions' },
                    ...versionOptions.map((v) => ({ value: v, label: v })),
                  ],
                }] : []),
              ]}
              toggles={[
                { id: 'findings', label: 'With open findings', checked: findingsOnly, onChange: setFindingsOnly },
              ]}
              onClear={hasFilters ? () => {
                setSearch('');
                setRgFilter('');
                setStateFilter('');
                setVersionFilter('');
                setFindingsOnly(false);
              } : undefined}
              resultCount={{
                shown: filtered.length,
                total: clustersTotal,
                label: 'clusters',
              }}
            />
          )}
          footer={filtered.length > 0 ? (
            <ResourceTableFooter
              shownCount={filtered.length}
              loadedCount={normalizedClusters.length}
              totalCount={clustersTotal}
              hasFilters={hasFilters}
              hasMore={hasMore}
              onLoadMore={loadMore}
              isLoadingMore={isLoadingMore}
            />
          ) : null}
        >
          <div className="card resource-table-card">
        {isLoading ? <LoadingState message="Loading AKS clusters…" /> :
         filtered.length === 0 ? (
          <EmptyState
            iconKey={PAGE_ICONS.aks}
            message={hasFilters
              ? 'No clusters match your filters.'
              : (isAdmin ? 'No AKS clusters in the database. Fetch from Azure to load and save inventory.' : 'No AKS clusters available yet. Ask an administrator to sync inventory from Azure.')}
          >
            {!hasFilters && (
              <AdminOnly>
                <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: '1rem', flexWrap: 'wrap' }}>
                  <FetchFromAzureButton onClick={handleSync} loading={syncing} disabled={!subscription} className="btn btn-primary" />
                </div>
              </AdminOnly>
            )}
          </EmptyState>
         ) : (
          <div className={resourceTableWrapClass(filtered.length)}>
            <table className="table resource-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Resource group</th>
                  <th>Location</th>
                  <th>Node pools</th>
                  <th>State</th>
                  <th>{costColumnLabel(currency)}</th>
                  <th>Advisor</th>
                  <th>Cost signals</th>
                  <th>Findings</th>
                </tr>
              </thead>
              <tbody>
                {groupedClusters.map(([rgName, groupRows]) => (
                  <React.Fragment key={rgName}>
                    <tr className="resource-group-header">
                      <td colSpan={8}>
                        <span className="resource-group-header__label">{rgName}</span>
                        <span className="resource-group-header__count">{groupRows.length}</span>
                      </td>
                    </tr>
                    {groupRows.map((c) => {
                      const clusterRid = rid(c);
                      const indexFindings = byResourceId.get(clusterRid) || [];
                      const cost = totalCost(c);
                      const isSelected = selected && rid(selected) === clusterRid;
                      return (
                        <tr
                          key={`${c.id || c.name}-${c.resourceGroup || ''}`}
                          className={`resource-table__row${isSelected ? ' resource-row--selected' : ''}`}
                          onClick={() => setSelected(c)}
                        >
                          <td>
                            <span className="icon-inline">
                              <AssetIcon src={PAGE_ICONS.aks} size={18} alt="" />
                              <span className="resource-name">{c.name}</span>
                            </span>
                          </td>
                          <td style={{ fontSize: '0.8rem', color: 'var(--text2)' }}>{c.resourceGroup || '—'}</td>
                          <td>{c.location}</td>
                          <td>{c._pools.length > 0 ? c._pools.length.toLocaleString() : '—'}</td>
                          <td><span style={{ color: STATE_COLOR[c._state] || 'var(--text2)', fontWeight: 600, fontSize: '0.8rem' }}>● {c._state}</span></td>
                          <td>
                            {cost > 0 ? <InlineCostCell amount={cost} row={c} currency={currency} /> : '—'}
                          </td>
                          <td>
                            <AdvisorTableCell
                              recommendations={lookupAdvisorForResource(advisorByResourceId, c)}
                              findings={indexFindings}
                              indexReady={advisorIndexReady && !advisorIndexLoading}
                              findingsIndexReady={indexReady}
                              isError={advisorIndexError}
                              subscriptionHasAdvisor={advisorByResourceId.size > 0}
                              subscriptionHasFindings={byResourceId.size > 0}
                            />
                          </td>
                          <td>
                            <InlineTriggerBadge findings={indexFindings} indexReady={indexReady} compact />
                          </td>
                          <td>
                            <InlineFindingBadge resource={c} indexFindings={indexFindings} savings={savingsByResource.get(clusterRid) || 0} currency={currency} indexReady={indexReady} />
                          </td>
                        </tr>
                      );
                    })}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
         )}
          </div>
        </ResourceInventoryPageShell>
      )}

      {!subscription && <SubscriptionRequired />}
      {subscription && isError && (
        <QueryErrorState error={error} onRetry={handleRefresh} title="Could not load AKS clusters" />
      )}

      <ResourceInsightDrawer
        resource={selectedCluster || selected}
        findings={selectedFindings}
        onClose={() => { setSelected(null); setDrawerFocus(null); }}
        title="AKS cluster"
        iconKey={PAGE_ICONS.aks}
        apiPath="/resources/aks"
        currency={currency}
        indexReady={indexReady}
        focusSection={drawerFocus}
      />
    </div>
  );
}

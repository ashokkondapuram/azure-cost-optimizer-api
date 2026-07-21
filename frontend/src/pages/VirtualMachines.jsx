import React, { useContext, useMemo, useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import AssetIcon from '../components/AssetIcon';
import FilterBar from '../components/FilterBar';
import FetchFromAzureButton from '../components/FetchFromAzureButton';
import AdminOnly from '../components/AdminOnly';
import InlineFindingBadge from '../components/visual/InlineFindingBadge';
import InlineCostCell from '../components/visual/InlineCostCell';
import ResourceInsightDrawer from '../components/ResourceInsightDrawer';
import VmSizingInsight from '../components/VmSizingInsight';
import useResourceSync from '../hooks/useResourceSync';
import usePaginatedResources from '../hooks/usePaginatedResources';
import useResourceSource from '../hooks/useResourceSource';
import useFindingsIndex from '../hooks/useFindingsIndex';
import useAdvisorIndex from '../hooks/useAdvisorIndex';
import usePersistedMetricTimespan from '../hooks/usePersistedMetricTimespan';
import AdvisorTableCell from '../components/advisor/AdvisorTableCell';
import InlineTriggerBadge from '../components/visual/InlineTriggerBadge';
import { lookupAdvisorForResource } from '../utils/resourceAdvisorUtils';
import { PAGE_ICONS } from '../config/assetIcons';
import { resourceMonthlyCost } from '../utils/costCurrency';
import { formatPowerState, toDisplayText } from '../utils/formatDisplay';
import {
  matchResourceRow, uniqueResourceGroups, resourceGroupOf,
} from '../utils/filterUtils';
import { hasRightsizingFinding, mergeLiveVmSizingFindings } from '../utils/sizingFindingsUtils';
import {
  resolveResourceFindings,
  resourceHasFindings,
} from '../utils/resourceFindingsUtils';
import { costColumnLabel } from '../config/resourceColumnConfig';
import ResourceInventoryShell from '../components/ResourceInventoryShell';
import ResourceInventoryPageShell from '../components/resources/ResourceInventoryPageShell';
import { FINDINGS_INDEX_LIMIT } from '../hooks/useFindingsIndex';
import { fetchVmSizing } from '../api/azure';
import { inventoryListSubtitle } from '../utils/viewerUi';
import { QueryErrorState, SubscriptionRequired, LoadingState, EmptyState } from '../components/QueryStates';
import ResourceTableFooter from '../components/table/ResourceTableFooter';
import useInventoryInspectDeepLink from '../hooks/useInventoryInspectDeepLink';
import { resourceTableWrapClass } from '../utils/resourceTableLayout';

const STATE_COLOR = { running: 'var(--success)', stopped: 'var(--warning)', deallocated: 'var(--text3)', starting: 'var(--accent)' };

export default function VirtualMachines() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get('search') || '');
  const [rgFilter, setRgFilter] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [findingsOnly, setFindingsOnly] = useState(false);
  const [tab, setTab] = useState('vms');
  const [selected, setSelected] = useState(null);
  const [drawerFocus, setDrawerFocus] = useState(null);
  const currency = billingCurrency || 'CAD';
  const { byResourceId, savingsByResource, truncated, indexReady, isError: findingsIndexError } = useFindingsIndex(subscription);
  const {
    byResourceId: advisorByResourceId,
    indexReady: advisorIndexReady,
    isLoading: advisorIndexLoading,
    isError: advisorIndexError,
  } = useAdvisorIndex(subscription);
  const { dataSource, isLive, resetToDatabase, isAdmin } = useResourceSource();

  const { sync, syncing } = useResourceSync({
    subscription,
    syncTypes: ['compute/vm', 'compute/disk'],
    includeCosts: false,
    invalidateKeys: [['/resources/vms', subscription], ['/resources/disks', subscription], ['resource-counts', subscription], ['findings-index', subscription], ['advisor-index', subscription]],
  });

  const {
    items: vms,
    total: vmsTotal,
    isLoading: loadVMs,
    isError: vmsError,
    error: vmsErr,
    refetch: refetchVMs,
    isFetching: fetchingVMs,
    hasMore: vmsHasMore,
    loadMore: loadMoreVms,
    isLoadingMore: loadingMoreVms,
  } = usePaginatedResources({
    apiPath: '/resources/vms',
    subscription,
    dataSource,
    enabled: !!subscription,
    includeProperties: true,
  });

  const {
    items: disks,
    total: disksTotal,
    isLoading: loadDisks,
    isError: disksError,
    error: disksErr,
    refetch: refetchDisks,
    isFetching: fetchingDisks,
    hasMore: disksHasMore,
    loadMore: loadMoreDisks,
    isLoadingMore: loadingMoreDisks,
  } = usePaginatedResources({
    apiPath: '/resources/disks',
    subscription,
    dataSource,
    enabled: !!subscription,
    includeProperties: true,
  });

  const handleSync = async () => {
    try {
      resetToDatabase();
      await sync();
      await Promise.all([refetchVMs(), refetchDisks()]);
    } catch {
      /* toast shown by hook */
    }
  };

  const handleRefresh = () => {
    resetToDatabase();
    refetchVMs();
    refetchDisks();
    queryClient.invalidateQueries({ queryKey: ['findings-index', subscription] });
    queryClient.invalidateQueries({ queryKey: ['advisor-index', subscription] });
  };

  const vmPowerState = (vm) => {
    const statuses = vm.properties?.instanceView?.statuses || [];
    const fromIv = statuses.find((s) => s.code?.startsWith('PowerState/'))?.code?.split('/')[1];
    if (fromIv) return fromIv;
    return formatPowerState(vm.properties?.powerState || vm.state);
  };

  const diskState = (d) => formatPowerState(d.properties?.diskState || d.state);
  const diskSku = (d) => toDisplayText(d.sku?.name || d.sku);
  const vmSize = (vm) => toDisplayText(vm.properties?.hardwareProfile?.vmSize || vm.sku);
  const rid = (item) => (item.id || item.resource_id || '').toLowerCase();

  useEffect(() => {
    const q = searchParams.get('search');
    if (q != null) setSearch(q);
  }, [searchParams]);

  const handleInspectOpen = useCallback((item, section) => {
    setSelected(item);
    setDrawerFocus(section || 'advanced-analysis');
  }, []);

  const inspectItems = tab === 'vms' ? vms : disks;
  const inspectLoading = tab === 'vms' ? loadVMs : loadDisks;
  const inspectHasMore = tab === 'vms' ? vmsHasMore : disksHasMore;
  const inspectLoadMore = tab === 'vms' ? loadMoreVms : loadMoreDisks;
  const inspectLoadingMore = tab === 'vms' ? loadingMoreVms : loadingMoreDisks;

  useInventoryInspectDeepLink({
    items: inspectItems,
    isLoading: inspectLoading,
    isLoadingMore: inspectLoadingMore,
    getResourceId: rid,
    hasMore: inspectHasMore,
    loadMore: inspectLoadMore,
    onOpen: handleInspectOpen,
    enabled: !!subscription,
  });

  const filterItem = (item, extraFields = []) => {
    if (!matchResourceRow(item, search, extraFields)) return false;
    if (rgFilter && resourceGroupOf(item) !== rgFilter) return false;
    if (findingsOnly && !resourceHasFindings(item, byResourceId.get(rid(item)) || [], { indexReady })) return false;
    return true;
  };

  const filteredVMs = vms.filter((v) => {
    if (!filterItem(v, [(row) => vmSize(row), (row) => vmPowerState(row)])) return false;
    if (stateFilter && vmPowerState(v) !== stateFilter) return false;
    return true;
  });
  const filteredDisks = disks.filter((d) => {
    if (!filterItem(d, [(row) => diskSku(row), (row) => diskState(row)])) return false;
    if (stateFilter && diskState(d) !== stateFilter) return false;
    return true;
  });

  const activeItems = tab === 'vms' ? vms : disks;
  const resourceGroups = uniqueResourceGroups(activeItems);
  const stateOptions = useMemo(() => {
    const states = tab === 'vms'
      ? vms.map(vmPowerState)
      : disks.map(diskState);
    return [...new Set(states.filter(Boolean))].sort();
  }, [tab, vms, disks]);

  const shownCount = tab === 'vms' ? filteredVMs.length : filteredDisks.length;
  const totalCount = tab === 'vms' ? vmsTotal : disksTotal;
  const summaryRows = tab === 'vms' ? filteredVMs : filteredDisks;
  const hasFilters = !!(search || rgFilter || stateFilter || findingsOnly);

  const groupByResourceGroup = (items) => {
    const groups = new Map();
    for (const r of items) {
      const rg = r.resourceGroup || r.resource_group || '—';
      if (!groups.has(rg)) groups.set(rg, []);
      groups.get(rg).push(r);
    }
    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  };

  const resourceGroup = (item) =>
    item.resourceGroup
    || (item.id || '').split('/').find((_, idx, arr) => arr[idx - 1]?.toLowerCase() === 'resourcegroups')
    || '';

  const monthlyCost = (item) => resourceMonthlyCost(item);

  const selectedRg = selected ? resourceGroup(selected) : '';
  const [vmSizingTimespan, onVmSizingTimespanChange] = usePersistedMetricTimespan(
    'finops-vmsizing-metrics-timespan',
  );
  const { data: vmSizingData } = useQuery({
    queryKey: ['vm-sizing', subscription, selectedRg, selected?.name, vmSizingTimespan],
    queryFn: () => fetchVmSizing({
      subscription_id: subscription,
      resource_group: selectedRg,
      vm_name: selected.name,
      timespan: vmSizingTimespan,
    }),
    enabled: !!subscription && tab === 'vms' && !!selected?.name && !!selectedRg,
    staleTime: 5 * 60_000,
  });

  const dbFindings = useMemo(() => {
    if (!selected) return [];
    return byResourceId.get(rid(selected)) || [];
  }, [selected, byResourceId]);

  const selectedFindings = useMemo(() => {
    if (!selected) return [];
    const base = resolveResourceFindings(selected, dbFindings, { indexReady });
    if (tab !== 'vms') return base;
    return mergeLiveVmSizingFindings(base, vmSizingData);
  }, [selected, dbFindings, tab, vmSizingData, indexReady]);

  const hideSizingRecommendation = useMemo(
    () => hasRightsizingFinding(dbFindings),
    [dbFindings],
  );

  const unattached = disks.filter((d) => diskState(d) === 'Unattached');
  const running = vms.filter((v) => vmPowerState(v) === 'running');
  const totalDisksGB = disks.reduce((s, d) => s + (d.properties?.diskSizeGB || 0), 0);
  const hasError = vmsError || disksError;
  const isFetching = fetchingVMs || fetchingDisks;
  const sourceLabel = inventoryListSubtitle({
    isAdmin,
    isLive,
    suffix: `${filteredVMs.length} of ${vmsTotal} VMs · ${filteredDisks.length} of ${disksTotal} disks`,
  });

  const isInventoryEmpty = !loadVMs && !loadDisks && vmsTotal === 0 && disksTotal === 0;
  const showInventoryStats = !isInventoryEmpty && (vmsTotal > 0 || disksTotal > 0);
  const vmPageChromeClass = showInventoryStats || !isInventoryEmpty || summaryRows.length > 0
    ? ' vm-inventory-page--has-chrome'
    : '';

  return (
    <div className={`page-shell vm-inventory-page vm-inventory-page--shell resource-inventory-page--shell${vmPageChromeClass}`}>
      <PageHeader
        title="Virtual machines & disks"
        iconSrc={PAGE_ICONS.vms}
        subtitle={subscription ? sourceLabel : 'Select a subscription'}
      >
        <AdminOnly>
          <FetchFromAzureButton onClick={handleSync} loading={syncing} disabled={!subscription} />
        </AdminOnly>
        <button type="button" className="btn btn-secondary" onClick={handleRefresh} disabled={!subscription || isFetching}>
          <RefreshCw size={13} className={isFetching ? 'spin' : ''} /> Refresh
        </button>
      </PageHeader>

      {subscription && !hasError && (
        <>
          {findingsIndexError && (
            <div className="alert alert--warning" role="status" style={{ marginBottom: '1rem' }}>
              Open findings are temporarily unavailable. Inventory and costs still load.
            </div>
          )}
          {showInventoryStats && (
            <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
              <div className="stat-card accent">
                <AssetIcon src={PAGE_ICONS.vmFleet} size={22} className="stat-card__icon" alt="" />
                <div className="stat-label">Total VMs</div>
                <div className="stat-value">{vmsTotal}</div>
                <div className="stat-sub">{running.length} running</div>
              </div>
              <div className="stat-card danger">
                <AssetIcon src={PAGE_ICONS.disks} size={22} className="stat-card__icon" alt="" />
                <div className="stat-label">Unattached disks</div>
                <div className="stat-value" style={{ color: 'var(--danger)' }}>{unattached.length}</div>
                <div className="stat-sub">Direct waste</div>
              </div>
              <div className="stat-card warning">
                <AssetIcon src={PAGE_ICONS.disks} size={22} className="stat-card__icon" alt="" />
                <div className="stat-label">Total disks</div>
                <div className="stat-value">{disksTotal}</div>
                <div className="stat-sub">{totalDisksGB.toLocaleString()} GB total</div>
              </div>
              <div className="stat-card success">
                <AssetIcon src={PAGE_ICONS.resourceGroup} size={22} className="stat-card__icon" alt="" />
                <div className="stat-label">Locations</div>
                <div className="stat-value">{[...new Set(vms.map(v => v.location))].length}</div>
                <div className="stat-sub">Unique Azure regions</div>
              </div>
            </div>
          )}
          {!isInventoryEmpty && (
            <div style={{ display: 'flex', gap: 8, marginBottom: '1rem' }}>
              <button type="button" className={`btn ${tab === 'vms' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => { setTab('vms'); setStateFilter(''); }}>
                <AssetIcon src={PAGE_ICONS.vms} size={14} alt="" /> VMs ({vmsTotal.toLocaleString()})
              </button>
              <button type="button" className={`btn ${tab === 'disks' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => { setTab('disks'); setStateFilter(''); }}>
                <AssetIcon src={PAGE_ICONS.disks} size={14} alt="" /> Disks ({disksTotal.toLocaleString()})
              </button>
            </div>
          )}
          {summaryRows.length > 0 && (
            <ResourceInventoryShell
              showFindingsSummary
              summaryRows={summaryRows}
              byResourceId={byResourceId}
              savingsByResource={savingsByResource}
              currency={currency}
              isAdmin={isAdmin}
              getResourceId={rid}
              truncated={truncated}
              indexReady={indexReady}
              findingsLimit={FINDINGS_INDEX_LIMIT}
              emptyAdminMessage="No open findings — sync and analyze in Sync center"
              emptyUserMessage={`No open findings for ${tab === 'vms' ? 'virtual machines' : 'disks'}`}
            />
          )}

        <ResourceInventoryPageShell
          toolbar={(
            <FilterBar
              search={{
                value: search,
                onChange: setSearch,
                placeholder: tab === 'vms' ? 'Search VMs by name, size, location…' : 'Search disks by name, SKU…',
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
                  label: tab === 'vms' ? 'Power state' : 'Disk state',
                  value: stateFilter,
                  onChange: setStateFilter,
                  options: [
                    { value: '', label: tab === 'vms' ? 'All power states' : 'All disk states' },
                    ...stateOptions.map((s) => ({ value: s, label: s })),
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
                setFindingsOnly(false);
              } : undefined}
              resultCount={{
                shown: shownCount,
                total: totalCount,
                label: tab === 'vms' ? 'VMs' : 'disks',
              }}
            />
          )}
          footer={
            tab === 'vms' && filteredVMs.length > 0 ? (
              <ResourceTableFooter
                shownCount={filteredVMs.length}
                loadedCount={vms.length}
                totalCount={vmsTotal}
                hasFilters={hasFilters}
                hasMore={vmsHasMore}
                onLoadMore={loadMoreVms}
                isLoadingMore={loadingMoreVms}
              />
            ) : tab === 'disks' && filteredDisks.length > 0 ? (
              <ResourceTableFooter
                shownCount={filteredDisks.length}
                loadedCount={disks.length}
                totalCount={disksTotal}
                hasFilters={hasFilters}
                hasMore={disksHasMore}
                onLoadMore={loadMoreDisks}
                isLoadingMore={loadingMoreDisks}
              />
            ) : null
          }
        >
          <div className="resource-inventory-panel">
        {tab === 'vms' && (
          loadVMs ? <LoadingState message="Loading virtual machines…" /> :
          filteredVMs.length === 0 ? (
            <EmptyState
              iconKey={PAGE_ICONS.vms}
              message={hasFilters
                ? 'No VMs match your filters.'
                : (isAdmin ? 'No VMs in the database. Fetch from Azure to load and save inventory.' : 'No VMs available yet. Ask an administrator to sync inventory from Azure.')}
            >
              {!hasFilters && (
                <AdminOnly>
                  <div className="resource-list-empty-actions">
                    <FetchFromAzureButton onClick={handleSync} loading={syncing} disabled={!subscription} className="btn btn-primary" />
                  </div>
                </AdminOnly>
              )}
            </EmptyState>
          ) : (
            <>
            <div className={resourceTableWrapClass(filteredVMs.length)}>
              <table className="table resource-table">
                <thead><tr><th>Name</th><th>Size</th><th>Location</th><th>OS</th><th>State</th><th>{costColumnLabel(currency)}</th><th>Advisor</th><th>Cost signals</th><th>Findings</th><th>Resource group</th></tr></thead>
                <tbody>
                  {groupByResourceGroup(filteredVMs).map(([rgName, groupRows]) => (
                    <React.Fragment key={rgName}>
                      <tr className="resource-group-header">
                        <td colSpan={10}>
                          <span className="resource-group-header__label">{rgName}</span>
                          <span className="resource-group-header__count">{groupRows.length}</span>
                        </td>
                      </tr>
                      {groupRows.map((vm) => {
                        const p = vm.properties || {};
                        const powerState = vmPowerState(vm);
                        const rg = resourceGroup(vm);
                        const vmRid = rid(vm);
                        const indexFindings = byResourceId.get(vmRid) || [];
                        const cost = monthlyCost(vm);
                        return (
                          <tr key={vm.id || vm.name} className="resource-table__row" onClick={() => setSelected(vm)}>
                            <td>
                              <span className="icon-inline">
                                <AssetIcon src={PAGE_ICONS.vms} size={18} alt="" />
                                <span className="resource-name">{vm.name}</span>
                              </span>
                            </td>
                            <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{vmSize(vm)}</td>
                            <td>{vm.location}</td>
                            <td>{p.storageProfile?.osDisk?.osType || '—'}</td>
                            <td>
                              <span style={{ color: STATE_COLOR[powerState] || 'var(--text2)', fontWeight: 600, fontSize: '0.8rem', textTransform: 'capitalize' }}>
                                ● {powerState}
                              </span>
                            </td>
                            <td>{cost > 0 ? <InlineCostCell amount={cost} row={vm} currency={currency} /> : '—'}</td>
                            <td>
                              <AdvisorTableCell
                                recommendations={lookupAdvisorForResource(advisorByResourceId, vm)}
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
                            <td><InlineFindingBadge resource={vm} indexFindings={indexFindings} savings={savingsByResource.get(vmRid) || 0} currency={currency} indexReady={indexReady} /></td>
                            <td style={{ color: 'var(--text3)' }}>{rg}</td>
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )
        )}
        {tab === 'disks' && (
          loadDisks ? <LoadingState message="Loading disks…" /> :
          filteredDisks.length === 0 ? (
            <EmptyState
              iconKey={PAGE_ICONS.disks}
              message={hasFilters
                ? 'No disks match your filters.'
                : (isAdmin ? 'No disks in the database. Fetch from Azure to load and save inventory.' : 'No disks available yet. Ask an administrator to sync inventory from Azure.')}
            >
              {!hasFilters && (
                <AdminOnly>
                  <div className="resource-list-empty-actions">
                    <FetchFromAzureButton onClick={handleSync} loading={syncing} disabled={!subscription} className="btn btn-primary" />
                  </div>
                </AdminOnly>
              )}
            </EmptyState>
          ) : (
            <>
            <div className={resourceTableWrapClass(filteredDisks.length)}>
              <table className="table resource-table">
                <thead><tr><th>Name</th><th>Size</th><th>SKU</th><th>State</th><th>{costColumnLabel(currency)}</th><th>Advisor</th><th>Cost signals</th><th>Findings</th><th>Location</th><th>Resource group</th></tr></thead>
                <tbody>
                  {groupByResourceGroup(filteredDisks).map(([rgName, groupRows]) => (
                    <React.Fragment key={rgName}>
                      <tr className="resource-group-header">
                        <td colSpan={10}>
                          <span className="resource-group-header__label">{rgName}</span>
                          <span className="resource-group-header__count">{groupRows.length}</span>
                        </td>
                      </tr>
                      {groupRows.map((d) => {
                        const p = d.properties || {};
                        const sku = diskSku(d);
                        const state = diskState(d);
                        const rg = resourceGroup(d);
                        const diskRid = rid(d);
                        const indexFindings = byResourceId.get(diskRid) || [];
                        const cost = monthlyCost(d);
                        return (
                          <tr key={d.id || d.name} className="resource-table__row" onClick={() => setSelected(d)}>
                            <td>
                              <span className="icon-inline">
                                <AssetIcon src={PAGE_ICONS.disks} size={18} alt="" />
                                <span className="resource-name" style={{ color: state === 'Unattached' ? 'var(--danger)' : undefined }}>{d.name}</span>
                              </span>
                            </td>
                            <td>{p.diskSizeGB || '—'} GB</td>
                            <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{sku}</td>
                            <td><span className={`badge ${state === 'Unattached' ? 'badge-critical' : 'badge-low'}`}>{state}</span></td>
                            <td>{cost > 0 ? <InlineCostCell amount={cost} row={d} currency={currency} /> : '—'}</td>
                            <td>
                              <AdvisorTableCell
                                recommendations={lookupAdvisorForResource(advisorByResourceId, d)}
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
                            <td><InlineFindingBadge resource={d} indexFindings={indexFindings} savings={savingsByResource.get(diskRid) || 0} currency={currency} indexReady={indexReady} /></td>
                            <td>{d.location}</td>
                            <td style={{ color: 'var(--text3)' }}>{rg}</td>
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )
        )}
          </div>
        </ResourceInventoryPageShell>
        </>
      )}

      {!subscription && <SubscriptionRequired />}

      {subscription && hasError && (
        <QueryErrorState
          error={vmsErr || disksErr}
          onRetry={() => {
            if (vmsError) refetchVMs();
            if (disksError) refetchDisks();
          }}
          title="Could not load inventory"
        />
      )}

      <ResourceInsightDrawer
        resource={selected}
        findings={selectedFindings}
        onClose={() => { setSelected(null); setDrawerFocus(null); }}
        title={tab === 'disks' ? 'Managed disk' : 'Virtual machine'}
        iconKey={tab === 'disks' ? PAGE_ICONS.disks : PAGE_ICONS.vms}
        apiPath={tab === 'disks' ? '/resources/disks' : '/resources/vms'}
        suppressLiveMetrics={tab === 'vms'}
        currency={currency}
        indexReady={indexReady}
        focusSection={drawerFocus}
      >
        {tab === 'vms' && selected && (
          <VmSizingInsight
            subscription={subscription}
            resourceGroup={resourceGroup(selected)}
            vmName={selected.name}
            enabled={!!subscription}
            data={vmSizingData}
            hideRecommendation={hideSizingRecommendation}
            currency={currency}
            timespan={vmSizingTimespan}
            onTimespanChange={onVmSizingTimespanChange}
          />
        )}
      </ResourceInsightDrawer>
    </div>
  );
}

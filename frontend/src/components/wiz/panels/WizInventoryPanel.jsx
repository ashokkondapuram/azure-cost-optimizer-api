import React, { useContext, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { AppCtx } from '../../../App';
import usePaginatedResources from '../../../hooks/usePaginatedResources';
import useFindingsIndex from '../../../hooks/useFindingsIndex';
import { fetchBilledResourceProperties } from '../../../api/azure';
import ResourceInsightDrawer from '../../ResourceInsightDrawer';
import AssetIcon from '../../AssetIcon';
import {
  LoadingState, EmptyState, QueryErrorState,
} from '../../QueryStates';
import { formatCurrency } from '../../../utils/format';
import { iconForRow, serviceDisplayNameForRow } from '../../../config/assetIcons';
import { resourceTotalCost } from '../../../utils/costCurrency';
import { resourceRowId, INVENTORY_API_PATH } from '../../../utils/resourceRowId';
import { resolveResourceFindings } from '../../../utils/resourceFindingsUtils';
import OptimizationGroupPanel from '../../optimization/OptimizationGroupPanel';
import WizResourceNameLink from '../WizResourceNameLink';
import {
  compareSeverity,
  formatCategoryLabel,
  groupResourceRows,
  resourceGroupLabelFromRow,
} from '../../../utils/taxonomy';
import WizGroupBySelect from '../WizGroupBySelect';

const API_PATH = INVENTORY_API_PATH;

function resourceId(row) {
  return resourceRowId(row);
}

function resourceGroup(row) {
  return resourceGroupLabelFromRow(row);
}

export default function WizInventoryPanel({ onTotalChange }) {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState(null);
  const [hydratingId, setHydratingId] = useState(null);
  const [serviceFilter, setServiceFilter] = useState('');
  const [issuesOnly, setIssuesOnly] = useState(false);
  const [sortBy, setSortBy] = useState('priority');
  const [groupBy, setGroupBy] = useState('');

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
  });

  const { byResourceId, savingsByResource, indexReady, truncated } = useFindingsIndex(subscription);

  React.useEffect(() => {
    if (typeof onTotalChange === 'function') onTotalChange(total);
  }, [total, onTotalChange]);

  const services = useMemo(() => {
    const set = new Set();
    for (const row of data) {
      const service = serviceDisplayNameForRow(row);
      if (service) set.add(service);
    }
    return [...set].sort();
  }, [data]);

  const rows = useMemo(() => {
    let list = (data || []).map((row) => {
      const rid = resourceId(row);
      const findings = rid ? byResourceId.get(rid) || [] : [];
      const savings = rid ? savingsByResource.get(rid) || 0 : 0;
      return {
        row,
        rec: {
          findings,
          findingCount: findings.length,
          savings,
          topFinding: findings[0] || null,
        },
      };
    });
    if (serviceFilter) {
      list = list.filter(({ row: r }) => serviceDisplayNameForRow(r) === serviceFilter);
    }
    if (issuesOnly) {
      list = list.filter(({ rec }) => rec.findingCount > 0);
    }
    if (q.trim()) {
      const hay = q.trim().toLowerCase();
      list = list.filter(({ row: r }) => {
        const text = `${r.name} ${r.id} ${serviceDisplayNameForRow(r)} ${r.type} ${resourceGroup(r)}`.toLowerCase();
        return text.includes(hay);
      });
    }
    const sorted = [...list];
    sorted.sort((a, b) => {
      if (sortBy === 'name') {
        return (a.row.name || '').localeCompare(b.row.name || '');
      }
      if (sortBy === 'cost') {
        return resourceTotalCost(b.row, currency) - resourceTotalCost(a.row, currency);
      }
      if (sortBy === 'issues') {
        return b.rec.findingCount - a.rec.findingCount;
      }
      if (sortBy === 'savings') {
        return b.rec.savings - a.rec.savings;
      }
      const severityDelta = compareSeverity(
        a.rec.topFinding?.severity,
        b.rec.topFinding?.severity,
      );
      if (severityDelta !== 0) return severityDelta;
      if (b.rec.savings !== a.rec.savings) return b.rec.savings - a.rec.savings;
      return (a.row.name || '').localeCompare(b.row.name || '');
    });
    return sorted;
  }, [data, q, serviceFilter, issuesOnly, byResourceId, savingsByResource, sortBy, currency]);

  const groupedRows = useMemo(
    () => groupResourceRows(rows, groupBy),
    [groupBy, rows],
  );

  const handleSelectRow = async (row) => {
    setSelected(row);
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

  const drawerFindings = useMemo(() => {
    if (!selected) return [];
    const rid = resourceId(selected);
    return resolveResourceFindings(
      selected,
      byResourceId.get(rid) || [],
      { indexReady },
    );
  }, [selected, byResourceId, indexReady]);

  if (!subscription) {
    return (
      <div className="wiz-empty">
        <strong>Select a subscription</strong>
        Choose a subscription to browse billed resources.
      </div>
    );
  }

  return (
    <div className="wiz-panel" id="wiz-panel-inventory" role="tabpanel" aria-labelledby="wiz-tab-inventory">
      <section className="wiz-card">
        <header className="wiz-card__head">
          <h3>Inventory</h3>
          <span className="wiz-pill">{(total ?? rows.length).toLocaleString()} resources</span>
        </header>
        <div className="wiz-toolbar">
          <span className="wiz-search" style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, opacity: 0.5 }} />
            <input
              type="search"
              placeholder="Search resources…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ paddingLeft: 30, width: '100%', maxWidth: 320 }}
              aria-label="Search inventory"
            />
          </span>
          <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} aria-label="Service filter">
            <option value="">All services</option>
            {services.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="Sort inventory">
            <option value="priority">Sort: priority</option>
            <option value="cost">Sort: cost</option>
            <option value="savings">Sort: savings</option>
            <option value="issues">Sort: issues</option>
            <option value="name">Sort: name</option>
          </select>
          <WizGroupBySelect value={groupBy} onChange={setGroupBy} />
          <label className="wiz-pill" style={{ cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={issuesOnly}
              onChange={(e) => setIssuesOnly(e.target.checked)}
              style={{ marginRight: 6 }}
            />
            With issues only
          </label>
        </div>

        {isLoading && <LoadingState message="Loading inventory…" />}
        {isError && <QueryErrorState error={error} onRetry={refetch} />}
        {!isLoading && !isError && rows.length === 0 && (
          <EmptyState message="No resources match your filters. Sync costs to populate inventory." />
        )}

        {!isLoading && !isError && rows.length > 0 && (
          <>
            <div className="wiz-table-wrap">
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
                            <th>Type</th>
                            <th>Resource group</th>
                            <th>Cost</th>
                            <th>Issues</th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.rows.map(({ row, rec }) => {
                            const rid = resourceId(row);
                            const cost = resourceTotalCost(row, currency);
                            const isHydrating = hydratingId === rid;
                            const category = row.categoryLabel
                              || formatCategoryLabel(row.category);
                            return (
                              <tr
                                key={rid || row.name}
                                className={selected && resourceId(selected) === rid ? 'wiz-row--selected' : ''}
                                onClick={() => handleSelectRow(row)}
                              >
                                <td>
                                  <div className="wiz-resource-cell">
                                    <AssetIcon iconKey={iconForRow(row, { apiPath: API_PATH })} size={20} />
                                    <div style={{ minWidth: 0 }}>
                                      <div className="wiz-resource-cell__name">
                                        <WizResourceNameLink resourceId={rid || row.id || row.resource_id} name={row.name}>
                                          {row.name}
                                          {isHydrating && <span style={{ marginLeft: 6, opacity: 0.6 }}>…</span>}
                                        </WizResourceNameLink>
                                      </div>
                                      <div className="wiz-resource-cell__meta">{row.location || '—'}</div>
                                    </div>
                                  </div>
                                </td>
                                <td>{serviceDisplayNameForRow(row) || '—'}</td>
                                <td>{category}</td>
                                <td style={{ fontSize: '0.75rem', color: 'var(--text2)' }}>{row.type || '—'}</td>
                                <td>{resourceGroup(row)}</td>
                                <td style={{ fontWeight: 600 }}>{formatCurrency(cost, { currency, decimals: 0 })}</td>
                                <td>
                                  {indexReady && rec.findingCount > 0 ? (
                                    <span className="wiz-pill wiz-pill--warn">
                                      {rec.findingCount}
                                      {rec.savings > 0 && ` · ${formatCurrency(rec.savings, { currency, decimals: 0 })}`}
                                    </span>
                                  ) : (
                                    <span className="wiz-pill wiz-pill--muted">—</span>
                                  )}
                                </td>
                              </tr>
                            );
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
                      <th>Type</th>
                      <th>Resource group</th>
                      <th>Cost</th>
                      <th>Issues</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(({ row, rec }) => {
                      const rid = resourceId(row);
                      const cost = resourceTotalCost(row, currency);
                      const isHydrating = hydratingId === rid;
                      const category = row.categoryLabel
                        || formatCategoryLabel(row.category);
                      return (
                        <tr
                          key={rid || row.name}
                          className={selected && resourceId(selected) === rid ? 'wiz-row--selected' : ''}
                          onClick={() => handleSelectRow(row)}
                        >
                          <td>
                            <div className="wiz-resource-cell">
                              <AssetIcon iconKey={iconForRow(row, { apiPath: API_PATH })} size={20} />
                              <div style={{ minWidth: 0 }}>
                                <div className="wiz-resource-cell__name">
                                  <WizResourceNameLink resourceId={rid || row.id || row.resource_id} name={row.name}>
                                    {row.name}
                                    {isHydrating && <span style={{ marginLeft: 6, opacity: 0.6 }}>…</span>}
                                  </WizResourceNameLink>
                                </div>
                                <div className="wiz-resource-cell__meta">{row.location || '—'}</div>
                              </div>
                            </div>
                          </td>
                          <td>{serviceDisplayNameForRow(row) || '—'}</td>
                          <td>{category}</td>
                          <td style={{ fontSize: '0.75rem', color: 'var(--text2)' }}>{row.type || '—'}</td>
                          <td>{resourceGroup(row)}</td>
                          <td style={{ fontWeight: 600 }}>{formatCurrency(cost, { currency, decimals: 0 })}</td>
                          <td>
                            {indexReady && rec.findingCount > 0 ? (
                              <span className="wiz-pill wiz-pill--warn">
                                {rec.findingCount}
                                {rec.savings > 0 && ` · ${formatCurrency(rec.savings, { currency, decimals: 0 })}`}
                              </span>
                            ) : (
                              <span className="wiz-pill wiz-pill--muted">—</span>
                            )}
                          </td>
                        </tr>
                      );
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

      {selected && (
        <ResourceInsightDrawer
          resource={selected}
          apiPath={API_PATH}
          findings={drawerFindings}
          indexReady={indexReady}
          currency={currency}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

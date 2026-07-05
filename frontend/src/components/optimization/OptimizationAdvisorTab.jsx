import React, { useContext, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Lightbulb, RefreshCw } from 'lucide-react';
import { AppCtx } from '../../App';
import useAdvisorIndex from '../../hooks/useAdvisorIndex';
import FilterBar from '../FilterBar';
import ResponsiveTableWrapper from '../responsive/ResponsiveTableWrapper';
import AdvisorRecommendationBadge from '../advisor/AdvisorRecommendationBadge';
import ArmResourceLink from '../ArmResourceLink';
import AdminOnly from '../AdminOnly';
import OptimizationGroupByToggle from './OptimizationGroupByToggle';
import OptimizationGroupPanel from './OptimizationGroupPanel';
import {
  advisorCategoryLabel,
  advisorMonthlySavings,
} from '../../utils/advisorUtils';
import {
  armResourceShortName,
} from '../../utils/resourceAdvisorUtils';
import {
  groupAdvisorByResourceGroup,
  groupAdvisorByResourceType,
} from '../../utils/optimizationGrouping';
import useOptimizationGroupBy from '../../hooks/useOptimizationGroupBy';
import { formatCurrency } from '../../utils/format';
import { appRouteForResourceId } from '../../utils/armResourceLinks';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../QueryStates';

const CATEGORY_OPTIONS = ['', 'Cost', 'Performance', 'HighAvailability', 'Security', 'OperationalExcellence'];
const IMPACT_OPTIONS = ['', 'High', 'Medium', 'Low'];

function AdvisorItemRow({ item, currency }) {
  const appRoute = appRouteForResourceId(item.resource_id);
  const savings = advisorMonthlySavings(item);
  return (
    <tr>
      <td>
        <div className="cell-stack">
          <strong>{armResourceShortName(item.resource_id)}</strong>
          <ArmResourceLink resourceId={item.resource_id} />
          {appRoute && (
            <Link to={appRoute} className="text-sm hub-advisor-inventory-link">
              Open in inventory
            </Link>
          )}
        </div>
      </td>
      <td>{advisorCategoryLabel(item.category)}</td>
      <td>
        <AdvisorRecommendationBadge recommendation={item} compact showSavings={false} currency={currency} />
      </td>
      <td className="hub-advisor-summary-cell">{item.summary}</td>
      <td>{savings > 0 ? formatCurrency(savings, { currency }) : '—'}</td>
    </tr>
  );
}

function AdvisorGroupedTable({ items, currency }) {
  return (
    <ResponsiveTableWrapper>
      <table className="data-table data-table--compact">
        <thead>
          <tr>
            <th>Resource</th>
            <th>Category</th>
            <th>Impact</th>
            <th>Summary</th>
            <th>Savings</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <AdvisorItemRow key={item.id || item.recommendation_id} item={item} currency={currency} />
          ))}
        </tbody>
      </table>
    </ResponsiveTableWrapper>
  );
}

export default function OptimizationAdvisorTab() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';

  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [impact, setImpact] = useState('');
  const [groupBy, setGroupBy] = useOptimizationGroupBy('resource_type');

  const {
    items,
    isLoading,
    isError,
    error,
    refetch,
    indexReady,
    hasData,
    truncated,
  } = useAdvisorIndex(subscription);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (category && item.category !== category) return false;
      if (impact && item.impact !== impact) return false;
      if (!q) return true;
      const hay = [
        item.summary,
        item.resource_id,
        item.category,
        item.impact,
        armResourceShortName(item.resource_id),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [items, search, category, impact]);

  const groupedByType = useMemo(() => groupAdvisorByResourceType(filtered), [filtered]);
  const groupedByRg = useMemo(() => groupAdvisorByResourceGroup(filtered), [filtered]);

  const totalSavings = useMemo(
    () => filtered.reduce((sum, item) => sum + (advisorMonthlySavings(item) || 0), 0),
    [filtered],
  );

  if (!subscription) return <SubscriptionRequired />;
  if (isLoading) return <LoadingState message="Loading Azure Advisor recommendations…" />;
  if (isError) return <QueryErrorState error={error} onRetry={refetch} />;

  return (
    <div className="optimization-hub-panel__content hub-advisor-tab">
      <div className="hub-advisor-tab__summary">
        <div className="hub-advisor-tab__stat">
          <span className="hub-advisor-tab__stat-label">Active recommendations</span>
          <strong>{filtered.length.toLocaleString()}</strong>
        </div>
        <div className="hub-advisor-tab__stat">
          <span className="hub-advisor-tab__stat-label">Groups</span>
          <strong>{(groupBy === 'resource_group' ? groupedByRg : groupedByType).length.toLocaleString()}</strong>
        </div>
        <div className="hub-advisor-tab__stat">
          <span className="hub-advisor-tab__stat-label">Potential savings</span>
          <strong>{totalSavings > 0 ? formatCurrency(totalSavings, { currency }) : '—'}</strong>
          <span className="text-muted text-sm">/mo</span>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => refetch()}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {!hasData && (
        <EmptyState iconKey="recommendations" message="No Azure Advisor recommendations synced yet.">
          <AdminOnly>
            <Link to="/admin/optimization" className="btn btn-primary btn-sm">
              Go to Optimization center
            </Link>
          </AdminOnly>
          <p className="text-muted text-sm hub-advisor-tab__hint">
            Run <strong>Sync Advisor</strong> to load recommendations into inventory Advisor columns.
          </p>
        </EmptyState>
      )}

      {hasData && (
        <>
          {truncated && (
            <div className="hub-advisor-tab__banner" role="status">
              Showing a capped subset. Narrow filters or increase sync coverage in Optimization center.
            </div>
          )}

          <FilterBar
            className="filter-bar--compact"
            search={{
              value: search,
              onChange: setSearch,
              placeholder: 'Search resource, summary, or type…',
            }}
            selects={[
              {
                id: 'category',
                label: 'Category',
                value: category,
                onChange: setCategory,
                options: CATEGORY_OPTIONS.map((v) => ({
                  value: v,
                  label: v ? advisorCategoryLabel(v) : 'All categories',
                })),
              },
              {
                id: 'impact',
                label: 'Impact',
                value: impact,
                onChange: setImpact,
                options: IMPACT_OPTIONS.map((v) => ({
                  value: v,
                  label: v || 'All impact levels',
                })),
              },
            ]}
            onClear={(search || category || impact) ? () => {
              setSearch('');
              setCategory('');
              setImpact('');
            } : undefined}
            resultCount={{
              shown: filtered.length,
              total: items.length !== filtered.length ? items.length : undefined,
              label: 'recommendations',
            }}
          />

          <div className="rec-view-toolbar no-print">
            <OptimizationGroupByToggle
              value={groupBy}
              onChange={setGroupBy}
              showFlat
            />
          </div>

          {filtered.length === 0 && (
            <EmptyState message="No Advisor recommendations match your filters." />
          )}

          {groupBy === 'resource_type' && filtered.length > 0 && (
            <div className="hub-advisor-groups">
              {groupedByType.map((group) => (
                <OptimizationGroupPanel
                  key={group.key}
                  title={group.label}
                  count={`${group.items.length} rec${group.items.length === 1 ? '' : 's'}`}
                  savings={group.savings}
                  currency={currency}
                >
                  <AdvisorGroupedTable items={group.items} currency={currency} />
                </OptimizationGroupPanel>
              ))}
            </div>
          )}

          {groupBy === 'resource_group' && filtered.length > 0 && (
            <div className="hub-advisor-groups">
              {groupedByRg.map((group) => (
                <OptimizationGroupPanel
                  key={group.key}
                  title={group.label}
                  count={`${group.items.length} rec${group.items.length === 1 ? '' : 's'}`}
                  savings={group.savings}
                  currency={currency}
                >
                  <AdvisorGroupedTable items={group.items} currency={currency} />
                </OptimizationGroupPanel>
              ))}
            </div>
          )}

          {groupBy === 'flat' && filtered.length > 0 && (
            <AdvisorGroupedTable items={filtered} currency={currency} />
          )}
        </>
      )}

      {!indexReady && hasData && (
        <p className="text-muted text-sm" role="status">Advisor index still loading…</p>
      )}
    </div>
  );
}

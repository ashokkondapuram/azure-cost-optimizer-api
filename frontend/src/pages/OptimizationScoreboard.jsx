import React, { useContext, useMemo, useState, Suspense, lazy, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { BarChart3, ChevronDown, RefreshCw } from 'lucide-react';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { useOptionalOptimizationHub } from '../context/OptimizationHubContext';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import FilterBar from '../components/FilterBar';
import AdminOnly from '../components/AdminOnly';
import ResourceInsightDrawer from '../components/ResourceInsightDrawer';
import OptimizationHubTabShell from '../components/optimization/OptimizationHubTabShell';
import ResourceTableFooter from '../components/table/ResourceTableFooter';
import ScoreboardTierBar from '../components/scoreboard/ScoreboardTierBar';
import ScoreboardTableRow from '../components/scoreboard/ScoreboardTableRow';
import SortableTableHeader from '../components/table/SortableTableHeader';
import useOptimizationScoreboard from '../hooks/useOptimizationScoreboard';
import { runAdvancedEngineScore } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { formatCurrency } from '../utils/format';
import { sortRows, toggleSort } from '../utils/clientSort';
import {
  averageScore,
  formatScore,
  TIER_ORDER,
  tierLabel,
} from '../utils/scoreboardUtils';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import ResponsiveTableWrapper from '../components/responsive/ResponsiveTableWrapper';
import { PAGE_ICONS } from '../config/assetIcons';
import { SAVINGS_SCOPE, SAVINGS_METRIC_SUB } from '../config/savingsScope';

const ScoreboardCharts = lazy(() => import('../components/scoreboard/ScoreboardCharts'));

const SCORE_FILTER_OPTIONS = [
  { value: '75', label: '75+' },
  { value: '60', label: '60+' },
  { value: '40', label: '40+' },
];

function resourceFromRow(row) {
  return {
    id: row.resource_id || row.id,
    resource_id: row.resource_id || row.id,
    name: row.resource_name,
    resource_name: row.resource_name,
    resource_type: row.resource_type,
    type: row.resource_type,
  };
}

export default function OptimizationScoreboard({ embedded = false }) {
  const { subscription, currency } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const hub = useOptionalOptimizationHub();

  const [tierFilter, setTierFilter] = useState('');
  const [minScore, setMinScore] = useState('');
  const [search, setSearch] = useState('');
  const [chartsOpen, setChartsOpen] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [detailResource, setDetailResource] = useState(null);
  const [sortKey, setSortKey] = useState('overall_recommendation_score');
  const [sortDir, setSortDir] = useState('desc');

  const filters = useMemo(() => ({
    ...(tierFilter ? { tier: tierFilter } : {}),
    ...(minScore ? { min_score: Number(minScore) } : {}),
  }), [tierFilter, minScore]);

  const {
    items,
    tierSummary,
    total,
    totalSavings,
    evaluationDate,
    isLoading,
    isError,
    error,
    refetch,
    indexReady,
    loadMore,
    hasMore,
    isLoadingMore,
    loadedCount,
  } = useOptimizationScoreboard(subscription, filters);

  const visibleItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = !q
      ? items
      : items.filter((row) => [
        row.resource_name,
        row.resource_type,
        row.resource_id,
        row.primary_action,
        row.recommendation_tier,
      ].join(' ').toLowerCase().includes(q));

    return sortRows(filtered, sortKey, sortDir);
  }, [items, search, sortKey, sortDir]);

  const avgScore = useMemo(() => averageScore(visibleItems), [visibleItems]);
  const hasFilters = Boolean(tierFilter || minScore || search);
  const heroSavings = hasFilters
    ? totalSavings
    : (hub?.estimatedMonthlySavings ?? totalSavings);

  const clearFilters = () => {
    setTierFilter('');
    setMinScore('');
    setSearch('');
  };

  const handleSort = useCallback((key) => {
    const next = toggleSort(sortKey, sortDir, key);
    setSortKey(next.key);
    setSortDir(next.direction);
  }, [sortKey, sortDir]);

  const scoreMutation = useMutation({
    mutationFn: () => runAdvancedEngineScore({ subscription_id: subscription }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-scoreboard'] });
      queryClient.invalidateQueries({ queryKey: ['optimization-trends'] });
      const scored = data?.scoring?.total ?? 0;
      toast.success(`Scored ${scored} resources`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  if (!subscription) return <SubscriptionRequired />;

  const hero = (
    <PageHero
      variant="scoreboard-hero"
      embedded={embedded}
      eyebrow="Resource scoring"
      title="Optimization scoreboard"
      subtitle="Review multi-dimensional scores, tiers, and recommended actions per resource."
      scopeNote={hasFilters ? SAVINGS_SCOPE.hubScoreboardFiltered : SAVINGS_SCOPE.hubScoreboard}
      isLoading={isLoading && !items.length}
      metrics={[
        {
          label: 'Scored',
          value: total.toLocaleString(),
          tone: 'default',
          sub: evaluationDate ? `As of ${evaluationDate}` : undefined,
          featured: true,
        },
        {
          label: 'Avg score',
          value: avgScore != null ? formatScore(avgScore) : '—',
          tone: avgScore != null && avgScore >= 60 ? 'success' : 'default',
          sub: visibleItems.length !== total ? 'Current view' : 'Subscription',
        },
        {
          label: 'Tier 1 safe',
          value: (tierSummary.tier1_safe || 0).toLocaleString(),
          tone: 'success',
          sub: 'Low-risk candidates',
        },
          {
            label: 'Est. savings',
            value: formatCurrency(heroSavings, { currency, decimals: 0 }),
            tone: 'success',
            sub: hasFilters ? SAVINGS_METRIC_SUB.scoreboardFiltered : SAVINGS_METRIC_SUB.unified,
          },
      ]}
      actions={isAdmin ? [{
        id: 'score',
        label: scoreMutation.isPending ? 'Scoring…' : 'Run advanced scoring',
        onClick: () => scoreMutation.mutate(),
        disabled: scoreMutation.isPending,
        primary: true,
        icon: <RefreshCw size={14} className={scoreMutation.isPending ? 'spin' : ''} />,
      }] : []}
    />
  );

  const toolbar = (
    <>
      <ScoreboardTierBar
        tierSummary={tierSummary}
        activeTier={tierFilter}
        onTierChange={setTierFilter}
        total={total}
      />
      <FilterBar
        search={{
          value: search,
          onChange: setSearch,
          placeholder: 'Search resources, types, or actions…',
        }}
        selects={[
          {
            id: 'tier',
            label: 'Tier',
            value: tierFilter,
            onChange: setTierFilter,
            options: TIER_ORDER.map((t) => ({ value: t, label: tierLabel(t) })),
          },
          {
            id: 'min-score',
            label: 'Min score',
            value: minScore,
            onChange: setMinScore,
            options: SCORE_FILTER_OPTIONS,
          },
        ]}
        onClear={hasFilters ? clearFilters : undefined}
        resultCount={{
          shown: visibleItems.length,
          total: search ? items.length : total,
          label: 'resources',
        }}
      />
    </>
  );

  const footer = items.length > 0 ? (
    <ResourceTableFooter
      shownCount={visibleItems.length}
      loadedCount={loadedCount}
      totalCount={total}
      hasFilters={hasFilters || Boolean(search.trim())}
      hasMore={hasMore}
      onLoadMore={loadMore}
      isLoadingMore={isLoadingMore}
      hint="Expand a row for details or use View for analysis"
    />
  ) : null;

  const body = (
    <>
      {visibleItems.length > 0 && (
        <section className="scoreboard-charts-section">
          <button
            type="button"
            className="scoreboard-charts-section__toggle"
            aria-expanded={chartsOpen}
            onClick={() => setChartsOpen((open) => !open)}
          >
            <BarChart3 size={16} aria-hidden />
            <span>Score distribution</span>
            <ChevronDown
              size={16}
              className={`scoreboard-charts-section__chevron${chartsOpen ? ' scoreboard-charts-section__chevron--open' : ''}`}
              aria-hidden
            />
          </button>
          {chartsOpen && (
            <Suspense fallback={<div className="chart-slot chart-slot--loading" aria-busy="true" aria-label="Loading charts" />}>
              <ScoreboardCharts
                items={visibleItems}
                tierSummary={tierSummary}
                activeTier={tierFilter}
                onTierClick={setTierFilter}
              />
            </Suspense>
          )}
        </section>
      )}

      {isLoading && <LoadingState message="Loading scoreboard…" />}
      {isError && <QueryErrorState error={error} onRetry={refetch} />}
      {indexReady && !items.length && (
        <EmptyState
          title="No scores yet"
          message={isAdmin
            ? 'Run advanced scoring after syncing Advisor and engine findings.'
            : 'Ask an admin to run advanced scoring for this subscription.'}
        />
      )}

      {indexReady && items.length > 0 && visibleItems.length === 0 && (
        <EmptyState message="No resources match your filters. Try clearing filters or broadening your search." />
      )}

      {visibleItems.length > 0 && (
        <section className="scoreboard-results" aria-label="Scored resources">
          <div className="scoreboard-results__head">
            <h2 className="scoreboard-results__title">Scored resources</h2>
            <p className="scoreboard-results__hint">
              Expand a row for the full dimension breakdown, or open View for advanced analysis.
            </p>
          </div>
          <ResponsiveTableWrapper>
            <div className="table-wrap scoreboard-table-wrap">
              <table className="data-table scoreboard-table">
                <thead>
                  <tr>
                    <SortableTableHeader
                      sortKey="resource_name"
                      activeKey={sortKey}
                      direction={sortDir}
                      onSort={handleSort}
                    >
                      Resource
                    </SortableTableHeader>
                    <SortableTableHeader
                      sortKey="overall_recommendation_score"
                      activeKey={sortKey}
                      direction={sortDir}
                      onSort={handleSort}
                    >
                      Score
                    </SortableTableHeader>
                    <th>Dimensions</th>
                    <SortableTableHeader
                      sortKey="primary_action"
                      activeKey={sortKey}
                      direction={sortDir}
                      onSort={handleSort}
                    >
                      Recommendation
                    </SortableTableHeader>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleItems.map((row) => (
                    <ScoreboardTableRow
                      key={row.id}
                      row={row}
                      currency={currency}
                      expanded={expandedId === row.id}
                      onToggleExpand={() => {
                        setExpandedId((current) => (current === row.id ? null : row.id));
                      }}
                      onOpenDetails={() => setDetailResource(resourceFromRow(row))}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </ResponsiveTableWrapper>
        </section>
      )}

      {total > 0 && (
        <p className="text-muted text-sm scoreboard-footnote">
          Advisory mode — scores inform rollout planning; no changes are applied automatically.
        </p>
      )}

      {detailResource && (
        <ResourceInsightDrawer
          resource={detailResource}
          onClose={() => setDetailResource(null)}
          currency={currency}
          focusSection="advanced-analysis"
        />
      )}
    </>
  );

  return (
    <div className={`page optimization-scoreboard-page${embedded ? '' : ''}`}>
      {!embedded && (
        <PageHeader
          title="Optimization scoreboard"
          subtitle="Multi-dimensional scores across cost, safety, effort, workload, and business"
          iconKey={PAGE_ICONS.scoreboard || 'recommendations'}
          actions={(
            <AdminOnly>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                disabled={scoreMutation.isPending}
                onClick={() => scoreMutation.mutate()}
              >
                <RefreshCw size={14} className={scoreMutation.isPending ? 'spin' : ''} />
                Run advanced scoring
              </button>
            </AdminOnly>
          )}
        />
      )}

      <OptimizationHubTabShell
        hero={hero}
        toolbar={toolbar}
        footer={footer}
        className={embedded ? '' : 'optimization-hub-tab-shell--standalone'}
      >
        {body}
      </OptimizationHubTabShell>
    </div>
  );
}

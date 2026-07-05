import React, { useContext, useMemo, useState, Suspense, lazy } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import FilterBar from '../components/FilterBar';
import AdminOnly from '../components/AdminOnly';
import ArmResourceLink from '../components/ArmResourceLink';
import MultiFacetScore from '../components/optimization/MultiFacetScore';
import OptimizationActionChip from '../components/optimization/OptimizationActionChip';
import ConfidenceScore from '../components/optimization/ConfidenceScore';
import useOptimizationScoreboard from '../hooks/useOptimizationScoreboard';
import { runAdvancedEngineScore } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { formatCurrency } from '../utils/format';
import { formatScore, tierLabel, tierTone, uniqueTiers } from '../utils/scoreboardUtils';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import { PAGE_ICONS } from '../config/assetIcons';
import { RefreshCw } from 'lucide-react';

const ScoreboardCharts = lazy(() => import('../components/scoreboard/ScoreboardCharts'));

const TIER_OPTIONS = ['tier1_safe', 'tier2_balanced', 'tier3_risky', 'blocked'];

export default function OptimizationScoreboard({ embedded = false }) {
  const { subscription, currency } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [tierFilter, setTierFilter] = useState('');
  const [minScore, setMinScore] = useState('');

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
  } = useOptimizationScoreboard(subscription, filters);

  const tiersPresent = useMemo(() => uniqueTiers(items), [items]);

  const scoreMutation = useMutation({
    mutationFn: () => runAdvancedEngineScore({ subscription_id: subscription }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-scoreboard'] });
      const scored = data?.scoring?.total ?? 0;
      toast.success(`Scored ${scored} resources`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  if (!subscription) return <SubscriptionRequired />;

  return (
    <div className={`page optimization-scoreboard-page${embedded ? ' optimization-hub-panel__content' : ''}`}>
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

      <PageHero
        variant="scoreboard-hero"
        eyebrow="Advanced engine"
        title="Optimization scoreboard"
        subtitle="Multi-dimensional scores across cost, safety, effort, workload, and business priority."
        isLoading={isLoading && !items.length}
        metrics={[
          {
            label: 'Scored',
            value: total.toLocaleString(),
            tone: 'default',
            sub: evaluationDate ? `As of ${evaluationDate}` : undefined,
          },
          {
            label: 'Tier 1 safe',
            value: (tierSummary.tier1_safe || 0).toLocaleString(),
            tone: 'success',
            sub: 'Low-risk candidates',
          },
          {
            label: 'Tier 2 balanced',
            value: (tierSummary.tier2_balanced || 0).toLocaleString(),
            tone: 'default',
          },
          {
            label: 'Est. savings',
            value: formatCurrency(totalSavings, { currency, decimals: 0 }),
            tone: 'success',
            sub: 'Current page',
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

      <FilterBar>
        <select className="filter-select" value={tierFilter} onChange={(e) => setTierFilter(e.target.value)}>
          <option value="">All tiers</option>
          {TIER_OPTIONS.map((t) => (
            <option key={t} value={t}>{tierLabel(t)}</option>
          ))}
        </select>
        <select className="filter-select" value={minScore} onChange={(e) => setMinScore(e.target.value)}>
          <option value="">Any overall score</option>
          <option value="75">75+</option>
          <option value="60">60+</option>
          <option value="40">40+</option>
        </select>
      </FilterBar>

      {items.length > 0 && (
        <Suspense fallback={<div className="chart-slot chart-slot--loading" aria-busy="true" aria-label="Loading charts" />}>
          <ScoreboardCharts items={items} tierSummary={tierSummary} />
        </Suspense>
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

      {items.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Resource</th>
                <th>Overall</th>
                <th>Tier</th>
                <th>Dimensions</th>
                <th>Action</th>
                <th>Est. savings</th>
                <th>Risk</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td>
                    <div className="cell-stack">
                      <strong>{row.resource_name}</strong>
                      <span className="text-muted text-sm">{row.resource_type}</span>
                      <ArmResourceLink resourceId={row.resource_id} />
                    </div>
                  </td>
                  <td>
                    <span className="scoreboard-overall">{formatScore(row.overall_recommendation_score)}</span>
                  </td>
                  <td>
                    <span className={`tier-pill tier-pill--${tierTone(row.recommendation_tier)}`}>
                      {tierLabel(row.recommendation_tier)}
                    </span>
                  </td>
                  <td className="scoreboard-dimensions-cell">
                    <MultiFacetScore
                      dimensions={row.dimensions}
                      overall={row.overall_recommendation_score}
                      compact
                    />
                  </td>
                  <td>
                    <OptimizationActionChip actionType={row.primary_action} compact />
                    <ConfidenceScore confidence={row.action_confidence} compact />
                  </td>
                  <td>
                    {row.cost_savings_monthly > 0
                      ? formatCurrency(row.cost_savings_monthly, { currency })
                      : '—'}
                  </td>
                  <td>{formatScore(row.performance_risk_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tiersPresent.length > 0 && (
        <p className="text-muted text-sm scoreboard-footnote">
          Advisory mode — scores inform rollout planning; no changes are applied automatically.
        </p>
      )}
    </div>
  );
}

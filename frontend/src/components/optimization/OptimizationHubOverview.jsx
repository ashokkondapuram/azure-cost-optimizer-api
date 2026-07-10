import React, { useContext, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Zap, BarChart3, Lightbulb, TrendingDown, ArrowRight, CheckCircle2,
  Target, Layers,
} from 'lucide-react';
import { AppCtx } from '../../App';
import { fetchFindingsSummary } from '../../api/azure';
import { fetchIdleSummary, fetchIdleSweep } from '../../api/wasteHeatmap';
import useAdvisorIndex from '../../hooks/useAdvisorIndex';
import useOptimizationActions from '../../hooks/useOptimizationActions';
import useOptimizationScoreboard from '../../hooks/useOptimizationScoreboard';
import { useOptimizationHub } from '../../context/OptimizationHubContext';
import useQueryWithTimeout from '../../hooks/useQueryWithTimeout';
import OptimizationHubTabShell from './OptimizationHubTabShell';
import PageHero from '../layout/PageHero';
import ActionLifecycle from './ActionLifecycle';
import HubMetricDrawer, { HubMetricRow, HubSeverityBars } from './HubMetricDrawer';
import HubWastePreview from './HubWastePreview';
import { SubscriptionRequired } from '../QueryStates';
import { formatCurrency } from '../../utils/format';
import { formatScore, tierLabel, tierTone } from '../../utils/scoreboardUtils';
import { actionResourceDisplayName, actionResourceTypeLabel } from '../../utils/actionUtils';
import { SAVINGS_SCOPE, SAVINGS_METRIC_SUB } from '../../config/savingsScope';
import { wasteHeatmapLink, heatmapCategoryFromEngine } from '../../utils/wasteHeatmapLinks';

function NextStepsCard({ proposedCount, onReview }) {
  return (
    <div className="next-steps-card">
      <h3>What&apos;s next?</h3>
      <ol>
        <li>Review {proposedCount.toLocaleString()} proposed actions</li>
        <li>Approve high-confidence savings</li>
        <li>Track execution on the scoreboard</li>
      </ol>
      <div className="next-steps__cta">
        <button type="button" className="btn btn-sm btn-primary" onClick={onReview}>
          <CheckCircle2 size={14} />
          Review actions
        </button>
      </div>
    </div>
  );
}

function HubStatCard({ label, value, sub, trend, tone = 'default', icon: Icon, onClick }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      className={`hub-stat-card hub-stat-card--${tone}${onClick ? ' hub-stat-card--clickable' : ''}`}
      onClick={onClick}
    >
      <span className="hub-stat-card__icon" aria-hidden><Icon size={18} /></span>
      <span className="hub-stat-card__body">
        <span className="hub-stat-card__label">{label}</span>
        <strong className="hub-stat-card__value">{value}</strong>
        {sub && <span className="hub-stat-card__sub">{sub}</span>}
        {trend && (
          <span className={`hub-stat-card__trend hub-stat-card__trend--${trend.direction}`}>
            {trend.direction === 'up' ? '↑' : '↓'} {trend.value}
          </span>
        )}
      </span>
      {onClick && <ArrowRight size={14} className="hub-stat-card__chevron" aria-hidden />}
    </Tag>
  );
}

const TIER_PREVIEW_ORDER = ['tier1_safe', 'tier2_balanced', 'tier3_risky', 'blocked'];

function HubScoreboardPreview({
  scoredTotal,
  avgScore,
  tierSummary,
  topItems,
  scoreboardSavings,
  evaluationDate,
  currency,
  onOpenScoreboard,
}) {
  const tierEntries = TIER_PREVIEW_ORDER
    .map((tier) => [tier, tierSummary[tier] || 0])
    .filter(([, count]) => count > 0);

  return (
    <section className="hub-rich-strip card hub-scoreboard-preview">
      <header className="hub-rich-strip__head hub-scoreboard-preview__head">
        <div className="hub-scoreboard-preview__title">
          <BarChart3 size={16} aria-hidden />
          <h3>Scoreboard snapshot</h3>
        </div>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onOpenScoreboard}>
          Open scoreboard
          <ArrowRight size={14} />
        </button>
      </header>

      {scoredTotal > 0 ? (
        <>
          <div className="hub-scoreboard-preview__stats">
            <div className="hub-scoreboard-preview__stat">
              <span className="hub-scoreboard-preview__stat-value">{scoredTotal.toLocaleString()}</span>
              <span className="hub-scoreboard-preview__stat-label">Resources scored</span>
            </div>
            <div className="hub-scoreboard-preview__stat">
              <span className="hub-scoreboard-preview__stat-value">
                {avgScore != null ? formatScore(avgScore) : '—'}
              </span>
              <span className="hub-scoreboard-preview__stat-label">Average score</span>
            </div>
            <div className="hub-scoreboard-preview__stat hub-scoreboard-preview__stat--savings">
              <span className="hub-scoreboard-preview__stat-value">
                {formatCurrency(scoreboardSavings, { currency, decimals: 0 })}
              </span>
              <span className="hub-scoreboard-preview__stat-label">Est. savings/mo</span>
            </div>
            {evaluationDate && (
              <div className="hub-scoreboard-preview__stat">
                <span className="hub-scoreboard-preview__stat-value hub-scoreboard-preview__stat-value--muted">
                  {evaluationDate}
                </span>
                <span className="hub-scoreboard-preview__stat-label">Evaluation date</span>
              </div>
            )}
          </div>

          {tierEntries.length > 0 && (
            <div className="hub-scoreboard-preview__tiers">
              {tierEntries.map(([tier, count]) => (
                <span key={tier} className={`hub-tier-chip hub-tier-chip--${tierTone(tier)}`}>
                  {tierLabel(tier)}
                  <strong>{count}</strong>
                </span>
              ))}
            </div>
          )}

          {topItems.length > 0 && (
            <ul className="hub-scoreboard-preview__list">
              {topItems.map((row) => (
                <li key={row.id} className="hub-scoreboard-preview__row">
                  <div className="hub-scoreboard-preview__resource">
                    <strong>{actionResourceDisplayName(row)}</strong>
                    <span className="text-muted text-sm">{actionResourceTypeLabel(row)}</span>
                  </div>
                  <span className={`tier-pill tier-pill--${tierTone(row.recommendation_tier)}`}>
                    {tierLabel(row.recommendation_tier)}
                  </span>
                  <span className="hub-scoreboard-preview__score">{formatScore(row.overall_recommendation_score)}</span>
                  <span className="hub-scoreboard-preview__savings">
                    {row.cost_savings_monthly > 0
                      ? formatCurrency(row.cost_savings_monthly, { currency, decimals: 0 })
                      : '—'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="hub-scoreboard-preview__empty">
          <p>No resources scored yet. Run advanced scoring to rank savings opportunities by tier and confidence.</p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenScoreboard}>
            Go to scoreboard
            <ArrowRight size={14} />
          </button>
        </div>
      )}
    </section>
  );
}

function SignalMixBar({ engineCount, advisorCount }) {
  const total = engineCount + advisorCount || 1;
  const enginePct = Math.round((engineCount / total) * 100);
  return (
    <div className="hub-signal-mix">
      <div className="hub-signal-mix__track">
        <div className="hub-signal-mix__engine" style={{ width: `${enginePct}%` }} title="Engine findings" />
        <div className="hub-signal-mix__advisor" style={{ width: `${100 - enginePct}%` }} title="Advisor" />
      </div>
      <div className="hub-signal-mix__legend">
        <span><i className="hub-signal-mix__dot hub-signal-mix__dot--engine" /> Engine {engineCount.toLocaleString()}</span>
        <span><i className="hub-signal-mix__dot hub-signal-mix__dot--advisor" /> Advisor {advisorCount.toLocaleString()}</span>
      </div>
    </div>
  );
}

export default function OptimizationHubOverview() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const { setTab, setActionsStatus, estimatedMonthlySavings: hubSavings, trends } = useOptimizationHub();
  const [drawer, setDrawer] = useState(null);

  const { data: findingsSummary } = useQueryWithTimeout({
    queryKey: ['findings-summary', subscription],
    queryFn: () => fetchFindingsSummary({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 60_000,
    timeout: 3000,
    allowEmpty: true,
  });

  const { data: idleSummary, isLoading: idleSummaryLoading } = useQueryWithTimeout({
    queryKey: ['idle-summary', subscription],
    queryFn: () => fetchIdleSummary(subscription),
    enabled: !!subscription,
    staleTime: 60_000,
    timeout: 5000,
    allowEmpty: true,
  });

  const { data: idleSweep, isLoading: idleSweepLoading } = useQueryWithTimeout({
    queryKey: ['idle-sweep', subscription],
    queryFn: () => fetchIdleSweep(subscription, { limit: 500 }),
    enabled: !!subscription,
    staleTime: 60_000,
    timeout: 8000,
    allowEmpty: true,
  });

  const {
    items: advisorItems,
    indexReady: advisorReady,
    hasData: hasAdvisorData,
  } = useAdvisorIndex(subscription);

  const {
    summary: actionsSummary,
    total: actionsTotal,
    isLoading: actionsLoading,
  } = useOptimizationActions(subscription, {}, { infinite: false, limit: 1 });

  const {
    items: scoreboardItems,
    tierSummary,
    total: scoreboardTotal,
    evaluationDate,
    indexReady: scoreboardReady,
  } = useOptimizationScoreboard(subscription, {}, { infinite: false, limit: 5 });

  const openFindings = findingsSummary?.open_findings ?? 0;
  const advisorCount = advisorReady ? advisorItems.length : 0;
  const unifiedSavings = findingsSummary?.unified_savings || {};
  const mergedSignalCount = unifiedSavings.merged_signal_count
    ?? unifiedSavings.resources_with_signals
    ?? openFindings;
  const unifiedMonthlySavings = unifiedSavings.unified_estimated_monthly_savings ?? 0;
  const savingsByActionClass = unifiedSavings.by_action_class || {};
  const overlapResources = unifiedSavings.resources_with_overlap ?? 0;
  const doubleCountAvoided = unifiedSavings.double_count_avoided_monthly ?? 0;
  const bySeverity = findingsSummary?.by_severity || {};
  const byCategory = findingsSummary?.by_category || {};

  const topCategories = useMemo(() => (
    Object.entries(byCategory)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
  ), [byCategory]);

  const scoredTotal = scoreboardTotal
    || trends?.resources_scored
    || trends?.scoring?.total
    || 0;

  const avgScore = useMemo(() => {
    if (trends?.scoring?.average_score != null) return trends.scoring.average_score;
    const scores = scoreboardItems
      .map((item) => item.overall_recommendation_score)
      .filter((score) => score != null);
    if (!scores.length) return null;
    return scores.reduce((sum, score) => sum + Number(score), 0) / scores.length;
  }, [trends, scoreboardItems]);

  const topScoreboardItems = useMemo(
    () => scoreboardItems.slice(0, 5),
    [scoreboardItems],
  );

  if (!subscription) return <SubscriptionRequired />;

  const proposed = actionsSummary?.proposed ?? 0;
  const approved = actionsSummary?.approved ?? 0;

  const handleWorkflowClick = (stepId, filter) => {
    if (filter) {
      setActionsStatus(filter);
    } else if (stepId === 'executing') {
      setActionsStatus('approved');
    } else {
      setTab('actions');
    }
  };

  return (
    <OptimizationHubTabShell
      className="hub-overview hub-overview--rich"
      hero={(
      <PageHero
        variant="hub-overview-hero"
        eyebrow="Optimization hub"
        title="Turn signals into savings"
        subtitle="Engine findings and Azure Advisor merge into actions — review confidence, approve changes, and track impact from one workspace."
        scopeNote={SAVINGS_SCOPE.hubOverview}
        metrics={[
          {
            label: 'Est. savings',
            value: formatCurrency(hubSavings, { currency, decimals: 0 }),
            tone: 'success',
            sub: SAVINGS_METRIC_SUB.unified,
            featured: true,
          },
          {
            label: 'Open findings',
            value: openFindings.toLocaleString(),
            tone: openFindings > 0 ? 'warning' : 'default',
            sub: 'Engine recommendations',
            href: '/optimization-hub?tab=actions',
          },
          {
            label: 'Actions',
            value: (actionsTotal || 0).toLocaleString(),
            tone: 'default',
            sub: `${proposed} proposed · ${approved} approved`,
          },
          {
            label: 'Resources scored',
            value: scoredTotal > 0 ? scoredTotal.toLocaleString() : (scoreboardReady ? '—' : '…'),
            tone: scoredTotal > 0 ? 'success' : 'default',
            sub: avgScore != null
              ? `Avg score ${formatScore(avgScore)}`
              : (scoredTotal > 0 ? 'Multi-dimensional scoring' : 'Run advanced scoring'),
          },
        ]}
        actions={[
          {
            id: 'review-actions',
            label: 'Review actions',
            href: '/optimization-hub?tab=actions',
            primary: true,
          },
          {
            id: 'recommendations',
            label: 'Recommendations',
            href: '/optimization-hub?tab=actions',
          },
          {
            id: 'waste-heatmap',
            label: 'Waste heatmap',
            href: '/waste-heatmap',
          },
        ]}
        footer={(
          <ActionLifecycle
            counts={actionsSummary}
            inObservation={approved}
            currency={currency}
            savings={hubSavings}
            onStepClick={handleWorkflowClick}
            compact
            className="hub-overview-lifecycle"
          />
        )}
      />
      )}
    >

      <div className="hub-overview-grid">
        <HubStatCard
          label="Optimization actions"
          value={(actionsTotal || 0).toLocaleString()}
          sub={`${proposed} proposed · ${formatCurrency(hubSavings, { currency, decimals: 0 })}/mo`}
          tone="actions"
          icon={Zap}
          onClick={() => setTab('actions')}
        />
        <HubStatCard
          label="Open findings"
          value={openFindings.toLocaleString()}
          sub={`${mergedSignalCount.toLocaleString()} resources with signals`}
          tone="findings"
          icon={Lightbulb}
          onClick={() => setDrawer('findings')}
        />
        <HubStatCard
          label="Scoreboard"
          value={scoredTotal > 0 ? scoredTotal.toLocaleString() : (scoreboardReady ? '—' : '…')}
          sub={avgScore != null
            ? `Average score ${formatScore(avgScore)}`
            : (tierSummary.tier1_safe ? `${tierSummary.tier1_safe} tier 1 safe` : 'Resource scoring')}
          tone="scoreboard"
          icon={BarChart3}
          onClick={() => setTab('scoreboard')}
        />
        <HubStatCard
          label="Signal mix"
          value={mergedSignalCount.toLocaleString()}
          sub={unifiedMonthlySavings > 0
            ? `${formatCurrency(unifiedMonthlySavings, { currency, decimals: 0 })}/mo unified`
            : 'Engine + Advisor'}
          tone="advisor"
          icon={Layers}
          onClick={() => setDrawer('signals')}
        />
        <NextStepsCard proposedCount={proposed} onReview={() => setTab('actions')} />
      </div>

      <section className="hub-rich-strip card">
        <header className="hub-rich-strip__head">
          <Target size={16} aria-hidden />
          <h3>Signal breakdown</h3>
        </header>
        <SignalMixBar engineCount={openFindings} advisorCount={advisorCount} />
        {topCategories.length > 0 && (
          <div className="hub-category-chips">
            {topCategories.map(([cat, count]) => (
              <Link
                key={cat}
                to={wasteHeatmapLink({ category: heatmapCategoryFromEngine(cat) || cat })}
                className="hub-category-chip hub-category-chip--link"
              >
                {cat.charAt(0) + cat.slice(1).toLowerCase()}
                <strong>{count}</strong>
              </Link>
            ))}
          </div>
        )}
      </section>

      <HubWastePreview
        idleSummary={idleSummary}
        idleSweep={idleSweep}
        loading={idleSummaryLoading || idleSweepLoading}
        currency={currency}
      />

      <HubScoreboardPreview
        scoredTotal={scoredTotal}
        avgScore={avgScore}
        tierSummary={tierSummary}
        topItems={topScoreboardItems}
        scoreboardSavings={hubSavings}
        evaluationDate={evaluationDate || trends?.evaluation_date}
        currency={currency}
        onOpenScoreboard={() => setTab('scoreboard')}
      />

      {!hasAdvisorData && (
        <div className="hub-overview-banner" role="status">
          <TrendingDown size={16} aria-hidden />
          <span>
            Advisor data is empty — actions may be engine-only until you run{' '}
            <strong>Sync Advisor</strong> in{' '}
            <Link to="/admin/optimization">Optimization center</Link>.
          </span>
        </div>
      )}

      {actionsLoading && actionsTotal === 0 && (
        <p className="hub-overview-hint text-muted text-sm">
          No actions yet. Run analysis, then use <strong>Run decision engine</strong> on the Actions tab.
        </p>
      )}

      <HubMetricDrawer
        open={drawer === 'findings'}
        title="Open findings"
        subtitle="Severity distribution from the optimization engine"
        onClose={() => setDrawer(null)}
      >
        <HubMetricRow label="Open total" value={openFindings.toLocaleString()} />
        <HubMetricRow
          label="Est. savings"
          value={formatCurrency(unifiedMonthlySavings || (findingsSummary?.total_estimated_savings_usd ?? 0), { currency, decimals: 0 })}
          tone="success"
        />
        {doubleCountAvoided > 0 && (
          <HubMetricRow
            label="Overlap removed"
            value={formatCurrency(doubleCountAvoided, { currency, decimals: 0 })}
            sub="Advisor + engine deduped"
          />
        )}
        <HubSeverityBars bySeverity={bySeverity} currency={currency} />
        <Link to="/waste-heatmap" className="btn btn-secondary btn-sm hub-metric-drawer__link">
          Open waste heatmap
          <ArrowRight size={14} />
        </Link>
        <Link to="/optimization-hub?tab=actions" className="btn btn-secondary btn-sm hub-metric-drawer__link">
          Open recommendations
          <ArrowRight size={14} />
        </Link>
      </HubMetricDrawer>

      <HubMetricDrawer
        open={drawer === 'signals'}
        title="Merged signals"
        subtitle="Engine findings and Advisor recommendations deduped per resource"
        onClose={() => setDrawer(null)}
      >
        <HubMetricRow label="Resources with signals" value={mergedSignalCount.toLocaleString()} />
        <HubMetricRow label="Engine findings" value={openFindings.toLocaleString()} />
        <HubMetricRow label="Advisor recommendations" value={advisorCount.toLocaleString()} />
        <HubMetricRow
          label="Unified est. savings"
          value={formatCurrency(unifiedMonthlySavings, { currency, decimals: 0 })}
          tone="success"
        />
        {overlapResources > 0 && (
          <HubMetricRow
            label="Resources in both sources"
            value={overlapResources.toLocaleString()}
            sub={doubleCountAvoided > 0 ? `${formatCurrency(doubleCountAvoided, { currency, decimals: 0 })} overlap removed` : undefined}
          />
        )}
        {Object.keys(savingsByActionClass).length > 0 && (
          <div className="hub-category-chips" style={{ marginTop: '0.75rem' }}>
            {Object.entries(savingsByActionClass).map(([actionClass, amount]) => (
              <span key={actionClass} className="hub-category-chip">
                {actionClass.replace(/_/g, ' ')}
                <strong>{formatCurrency(amount, { currency, decimals: 0 })}</strong>
              </span>
            ))}
          </div>
        )}
        <SignalMixBar engineCount={openFindings} advisorCount={advisorCount} />
        <button type="button" className="btn btn-secondary btn-sm hub-metric-drawer__link" onClick={() => { setDrawer(null); setTab('actions'); }}>
          Review merged actions
          <ArrowRight size={14} />
        </button>
      </HubMetricDrawer>
    </OptimizationHubTabShell>
  );
}

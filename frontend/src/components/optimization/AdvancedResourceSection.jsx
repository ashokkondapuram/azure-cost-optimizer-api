import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Gauge } from 'lucide-react';
import { fetchResourceAdvancedAnalysis } from '../../api/azure';
import DrawerCollapsibleSection from '../DrawerCollapsibleSection';
import { DrawerSectionSkeleton } from '../DrawerBodySkeleton';
import MultiFacetScore from './MultiFacetScore';
import OptimizationActionChip from './OptimizationActionChip';
import { SeverityIcon } from '../FinOpsIcons';
import { formatCurrency } from '../../utils/format';
import { tierLabel, tierTone, formatScore } from '../../utils/scoreboardUtils';

function WorkloadSummary({ profile }) {
  if (!profile) return <p className="text-muted text-sm">No workload profile yet. Run advanced scoring.</p>;
  return (
    <dl className="advanced-analysis-dl">
      <div><dt>Type</dt><dd>{profile.workload_type || '—'}</dd></div>
      <div><dt>Burstiness</dt><dd>{formatScore(profile.burstiness_score)}</dd></div>
      <div><dt>Peak factor</dt><dd>{profile.peak_hour_factor ?? '—'}</dd></div>
      <div><dt>Trend</dt><dd>{profile.utilization_trend || '—'}</dd></div>
      {profile.detected_seasonality && (
        <div><dt>Seasonality</dt><dd>Detected</dd></div>
      )}
    </dl>
  );
}

function DependencySummary({ dependencies }) {
  if (!dependencies) return null;
  return (
    <dl className="advanced-analysis-dl">
      <div><dt>Blast radius</dt><dd>{dependencies.blast_radius ?? 0}</dd></div>
      <div><dt>Max criticality</dt><dd>{dependencies.max_criticality || '—'}</dd></div>
      <div><dt>SLA tier</dt><dd>{dependencies.sla_tier || '—'}</dd></div>
      {dependencies.compliance_locked && (
        <div><dt>Compliance</dt><dd>Locked</dd></div>
      )}
    </dl>
  );
}

function ActionableFindings({ findings, currency }) {
  if (!findings?.length) {
    return (
      <p className="text-muted text-sm">
        No high-value optimization signals yet. Run analysis with Azure Monitor metrics
        synced for rightsizing and cost-backed recommendations.
      </p>
    );
  }

  return (
    <ul className="advanced-analysis-findings">
      {findings.map((finding) => (
        <li key={finding.id || finding.rule_id} className="advanced-analysis-finding">
          <div className="advanced-analysis-finding__header">
            <SeverityIcon severity={finding.severity} size={14} />
            <span className="advanced-analysis-finding__title">
              {finding.rule_name || finding.rule_id}
            </span>
            {finding.estimated_savings_usd > 0 && (
              <span className="advanced-analysis-finding__savings">
                {formatCurrency(finding.estimated_savings_usd, { currency })}/mo
              </span>
            )}
          </div>
          <p className="advanced-analysis-finding__detail">{finding.detail}</p>
          {finding.recommendation && (
            <p className="advanced-analysis-finding__rec text-muted text-sm">
              {finding.recommendation}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function AdvancedResourceSection({
  resourceId,
  subscriptionId,
  currency = 'USD',
  prefetchedData = undefined,
  prefetchedLoading = false,
  prefetchedError = null,
}) {
  const usePrefetch = prefetchedData !== undefined || prefetchedLoading;
  const { data: queryData, isLoading: queryLoading, isError: queryError } = useQuery({
    queryKey: ['resource-advanced-analysis', subscriptionId, resourceId],
    queryFn: () => fetchResourceAdvancedAnalysis({
      subscription_id: subscriptionId,
      resource_id: resourceId,
    }),
    enabled: Boolean(subscriptionId && resourceId) && !usePrefetch,
    staleTime: 120_000,
  });

  const data = usePrefetch ? prefetchedData : queryData;
  const isLoading = usePrefetch ? prefetchedLoading : queryLoading;
  const isError = usePrefetch ? !!prefetchedError : queryError;

  const scorecard = data?.scorecard;
  const actionableFindings = data?.actionable_findings || [];
  const hasWorkload = Boolean(data?.workload_profile?.workload_type);
  const hasDependencies = Boolean(
    data?.dependencies && (
      data.dependencies.blast_radius
      || data.dependencies.max_criticality
      || data.dependencies.sla_tier
    ),
  );
  const hasTrends = Boolean(data?.trends?.cost_trajectory);
  const hasContent = Boolean(
    scorecard || hasWorkload || hasDependencies || hasTrends || actionableFindings.length,
  );

  return (
    <DrawerCollapsibleSection
      title="Advanced analysis"
      icon={<Gauge size={13} />}
      variant="info"
      defaultOpen={Boolean(scorecard || hasWorkload)}
      compact
      badge={scorecard ? formatScore(scorecard.overall_recommendation_score) : null}
      hint="Evidence-backed optimization signals from workload, cost, and monitor data."
    >
      {isLoading && <DrawerSectionSkeleton rows={3} />}
      {isError && <p className="text-muted text-sm">Could not load advanced analysis.</p>}
      {!isLoading && !isError && !hasContent && (
        <div className="advanced-resource-empty">
          <p className="text-muted text-sm">
            No advanced score yet for this resource. Run advanced scoring to populate workload,
            dependency, and optimization scores.
          </p>
          <Link to="/optimization-hub?tab=scoreboard" className="btn btn--ghost btn--sm">
            Open scoreboard
          </Link>
        </div>
      )}
      {data && hasContent && (
        <div className="advanced-resource-section">
          {scorecard && (
            <>
              <div className="advanced-resource-section__header">
                <span className={`tier-pill tier-pill--${tierTone(scorecard.recommendation_tier)}`}>
                  {tierLabel(scorecard.recommendation_tier)}
                </span>
                <OptimizationActionChip actionType={scorecard.primary_action} compact />
                {scorecard.cost_savings_monthly > 0 && (
                  <span className="text-sm">
                    {formatCurrency(scorecard.cost_savings_monthly, { currency })}/mo
                  </span>
                )}
              </div>
              <MultiFacetScore
                dimensions={scorecard.dimensions}
                overall={scorecard.overall_recommendation_score}
              />
            </>
          )}
          {!scorecard && (
            <p className="text-muted text-sm advanced-resource-section__hint">
              Run advanced scoring to generate a multi-facet optimization scorecard.
            </p>
          )}
          <div className="advanced-resource-section__findings">
            <h4 className="advanced-resource-section__subtitle">Actionable findings</h4>
            <ActionableFindings findings={actionableFindings} currency={currency} />
          </div>
          <div className="advanced-resource-section__grid">
            <div>
              <h4 className="advanced-resource-section__subtitle">Workload</h4>
              <WorkloadSummary profile={data.workload_profile} />
            </div>
            <div>
              <h4 className="advanced-resource-section__subtitle">Dependencies</h4>
              <DependencySummary dependencies={data.dependencies} />
            </div>
          </div>
          {data.trends?.cost_trajectory && (
            <p className="text-muted text-sm">
              Cost trend: {data.trends.cost_trajectory}
              {data.trends.cost_vs_prev_month_pct != null && ` (${data.trends.cost_vs_prev_month_pct}%)`}
            </p>
          )}
          <Link to="/optimization-hub?tab=scoreboard" className="btn btn--ghost btn--sm">
            View scoreboard
          </Link>
        </div>
      )}
    </DrawerCollapsibleSection>
  );
}

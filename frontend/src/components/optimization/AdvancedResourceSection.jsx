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

function InsightCard({ item }) {
  if (!item) return null;
  return (
    <article className={`advanced-insight advanced-insight--${item.tone || 'neutral'}`}>
      <div className="advanced-insight__top">
        <span className="advanced-insight__label">{item.label}</span>
        <strong className="advanced-insight__value">{item.value}</strong>
      </div>
      {item.detail && <p className="advanced-insight__detail">{item.detail}</p>}
    </article>
  );
}

function InsightGroup({ title, items }) {
  if (!items?.length) return null;
  return (
    <section className="advanced-insight-group">
      <h4 className="advanced-resource-section__subtitle">{title}</h4>
      <div className="advanced-insight-grid">
        {items.map((item) => (
          <InsightCard key={`${title}-${item.label}`} item={item} />
        ))}
      </div>
    </section>
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
  forceOpen = false,
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
  const insights = data?.insights;
  const hasInsights = Boolean(
    insights?.workload?.length
    || insights?.dependencies?.length
    || insights?.cost?.length,
  );
  const hasContent = Boolean(
    scorecard || hasInsights || actionableFindings.length,
  );

  return (
    <DrawerCollapsibleSection
      title="Advanced analysis"
      icon={<Gauge size={13} />}
      variant="info"
      defaultOpen={forceOpen || Boolean(scorecard || hasInsights)}
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

          {insights?.headline && (
            <p className="advanced-insight-headline">{insights.headline}</p>
          )}

          <InsightGroup title="Workload" items={insights?.workload} />
          <InsightGroup title="Dependencies" items={insights?.dependencies} />
          <InsightGroup title="Cost" items={insights?.cost} />

          <div className="advanced-resource-section__findings">
            <h4 className="advanced-resource-section__subtitle">Actionable findings</h4>
            <ActionableFindings findings={actionableFindings} currency={currency} />
          </div>

          <Link to="/optimization-hub?tab=scoreboard" className="btn btn--ghost btn--sm">
            View scoreboard
          </Link>
        </div>
      )}
    </DrawerCollapsibleSection>
  );
}

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Gauge } from 'lucide-react';
import { fetchResourceAdvancedAnalysis } from '../../api/azure';
import { DrawerSectionSkeleton } from '../DrawerBodySkeleton';
import OptimizationActionChip from './OptimizationActionChip';
import { SeverityIcon } from '../FinOpsIcons';
import { formatCurrency } from '../../utils/format';
import { formatUtilizationTrend } from '../../utils/evidenceUtils';

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
        synced for rightsizing and cost-backed findings.
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

function hasInsightContent(data) {
  if (!data) return false;
  const insights = data.insights;
  const trends = data.trends;
  const actionableFindings = data.actionable_findings || [];
  return Boolean(
    insights?.headline
    || insights?.workload?.length
    || insights?.dependencies?.length
    || insights?.cost?.length
    || trends?.cpu_trend
    || trends?.memory_trend
    || trends?.cost_vs_prev_month_pct != null
    || actionableFindings.length,
  );
}

export default function AdvancedResourceSection({
  resourceId,
  subscriptionId,
  currency = 'USD',
  prefetchedData = undefined,
  prefetchedLoading = false,
  prefetchedError = null,
  bare = false,
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

  const scorecard = bare ? null : data?.scorecard;
  const actionableFindings = data?.actionable_findings || [];
  const insights = data?.insights;
  const hasContent = bare ? hasInsightContent(data) : Boolean(scorecard || hasInsightContent(data));

  const body = (
    <>
      {isLoading && <DrawerSectionSkeleton rows={3} />}
      {isError && <p className="text-muted text-sm">Could not load resource insights.</p>}
      {!isLoading && !isError && !hasContent && (
        <div className="advanced-resource-empty">
          <p className="text-muted text-sm">
            {bare
              ? 'No workload or cost insights yet. Sync Azure Monitor metrics for utilization-backed signals.'
              : 'No advanced insights yet for this resource. Sync metrics and run analysis to populate signals.'}
          </p>
          {!bare && (
            <Link to="/action-centre?hasAction=1" className="btn btn--ghost btn--sm">
              Proposed actions
            </Link>
          )}
        </div>
      )}
      {data && hasContent && (
        <div className="advanced-resource-section">
          {!bare && scorecard && (
            <div className="advanced-resource-section__header">
              <OptimizationActionChip actionType={scorecard.primary_action} compact />
              {scorecard.cost_savings_monthly > 0 && (
                <span className="text-sm">
                  {formatCurrency(scorecard.cost_savings_monthly, { currency })}/mo
                </span>
              )}
            </div>
          )}

          {insights?.headline && (
            <p className="advanced-insight-headline">{insights.headline}</p>
          )}

          <InsightGroup title="Workload" items={insights?.workload} />
          <InsightGroup title="Dependencies" items={insights?.dependencies} />
          <InsightGroup title="Cost" items={insights?.cost} />

          {insights?.data_quality && (
            <div className="wiz-assessment__alert" role="status" style={{ marginBottom: '0.75rem' }}>
              <span>
                Monitor data:
                {' '}
                {insights.data_quality.has_monitor_data ? 'available' : 'missing'}
                {insights.data_quality.insufficient_history ? ' · insufficient history' : ''}
              </span>
            </div>
          )}

          {data.utilization_evidence && !bare && (
            <InsightGroup
              title="Utilization evidence"
              items={[
                data.utilization_evidence.avg_cpu_pct != null && {
                  label: 'Avg CPU',
                  value: `${data.utilization_evidence.avg_cpu_pct}%`,
                },
                data.utilization_evidence.max_cpu_pct != null && {
                  label: 'Peak CPU',
                  value: `${data.utilization_evidence.max_cpu_pct}%`,
                },
                data.utilization_evidence.avg_memory_pct != null && {
                  label: 'Avg memory',
                  value: `${data.utilization_evidence.avg_memory_pct}%`,
                },
                data.utilization_evidence.max_memory_pct != null && {
                  label: 'Peak memory',
                  value: `${data.utilization_evidence.max_memory_pct}%`,
                },
              ].filter(Boolean)}
            />
          )}

          {data.trends && (
            <InsightGroup
              title="Trends"
              items={[
                data.trends.cpu_trend && {
                  label: 'CPU trend',
                  value: formatUtilizationTrend(data.trends.cpu_trend),
                },
                data.trends.memory_trend && {
                  label: 'Memory trend',
                  value: formatUtilizationTrend(data.trends.memory_trend),
                },
                data.trends.cost_vs_prev_month_pct != null && {
                  label: 'Cost vs last month',
                  value: `${data.trends.cost_vs_prev_month_pct}%`,
                },
              ].filter((item) => item && item.value)}
            />
          )}

          {!bare && actionableFindings.length > 0 && (
            <div className="advanced-resource-section__findings">
              <h4 className="advanced-resource-section__subtitle">Actionable findings</h4>
              <ActionableFindings findings={actionableFindings} currency={currency} />
            </div>
          )}

          {!bare && (
            <Link to="/action-centre?hasAction=1" className="btn btn--ghost btn--sm">
              View proposed actions
            </Link>
          )}
        </div>
      )}
    </>
  );

  if (bare) {
    return <div className="insight-drawer__bare-content">{body}</div>;
  }

  return (
    <div className="insight-drawer__inline-section insight-drawer__analysis-section">
      <div className="insight-drawer__property-group-title insight-drawer__inline-section-head">
        <span className="insight-drawer__inline-section-title">
          <Gauge size={13} aria-hidden />
          Advanced analysis
        </span>
      </div>
      <p className="insight-drawer__inline-section-hint text-muted text-sm">
        Evidence-backed optimization signals from workload, cost, and monitor data.
      </p>
      {body}
    </div>
  );
}

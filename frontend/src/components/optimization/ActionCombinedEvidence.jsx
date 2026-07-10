import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatCurrency } from '../../utils/format';
import {
  parseActionAnalysis,
  tierLabel,
  tierTone,
  optimizationDataQualityLabel,
  optimizationMetricStatusLabel,
} from '../../utils/actionAnalysisUtils';
import ActionEvidenceSignals from './ActionEvidenceSignals';
import ResourceMetricsTimespanFilter from '../ResourceMetricsTimespanFilter';
import usePersistedMetricTimespan from '../../hooks/usePersistedMetricTimespan';
import { fetchResourceAzureMetrics } from '../../api/azure';
import { liveMetricsToEvidencePerformance } from '../../utils/resourceMetricsUtils';
import { metricTimespanLabel } from '../../utils/metricsTimespanUtils';

const ACTION_METRICS_TIMESPAN_KEY = 'optimization-action-metrics-timespan';

function DimensionRow({ label, value }) {
  if (value == null) return null;
  const pct = Math.round(Number(value));
  return (
    <div className="action-analysis-dimension">
      <div className="action-analysis-dimension__header">
        <span>{label}</span>
        <span>{pct}</span>
      </div>
      <div className="action-analysis-dimension__track">
        <div
          className="action-analysis-dimension__fill"
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  );
}

function MetricsTable({ title, metrics }) {
  if (!metrics?.length) return null;
  return (
    <div className="drawer-investigation">
      <h4 className="drawer-investigation__title">{title}</h4>
      <table className="finding-evidence__table finding-evidence__metrics-table">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">Value</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => (
            <tr key={metric.id || metric.label}>
              <td>{metric.label}</td>
              <td>{metric.formatted ?? metric.value ?? '—'}</td>
              <td>{optimizationMetricStatusLabel(metric.status) || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ActionCombinedEvidence({
  action,
  currency = 'USD',
  showSignals = true,
  compact = false,
}) {
  const [timespan, onTimespanChange] = usePersistedMetricTimespan(ACTION_METRICS_TIMESPAN_KEY);
  const resourceId = action?.resource_id || '';
  const canFetchLiveMetrics = Boolean(resourceId);
  const { data: liveMetrics, isFetching: liveMetricsFetching } = useQuery({
    queryKey: ['resource-azure-metrics', resourceId, timespan],
    queryFn: () => fetchResourceAzureMetrics({ resource_id: resourceId, timespan }),
    enabled: !!action && canFetchLiveMetrics && !!timespan,
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const livePerformanceMetrics = useMemo(
    () => liveMetricsToEvidencePerformance(liveMetrics),
    [liveMetrics],
  );

  if (!action) return null;

  const analysis = parseActionAnalysis(action);
  const summary = action.evidence_summary;
  const {
    cost,
    utilization,
    metrics,
    rules,
    tier,
    dimensions,
    workload,
    dataQuality,
  } = analysis;

  const performanceMetrics = livePerformanceMetrics.length
    ? livePerformanceMetrics
    : metrics?.performance;
  const comparisonDays = cost.combined_evidence?.comparison_window_days
    || cost.comparison_window_days;

  const combined = cost.combined_evidence || {};
  const hasContent = Boolean(
    cost.current_monthly_cost
    || metrics?.cost?.length
    || metrics?.performance?.length
    || rules.length
    || summary?.has_advisor
    || summary?.has_findings
    || summary?.has_metrics,
  );

  return (
    <section className={`drawer-section${compact ? ' drawer-section--compact' : ''}`}>
      <div className="drawer-section__head">
        <h3 className="drawer-section__title">{compact ? 'Analysis' : 'Combined analysis'}</h3>
        {canFetchLiveMetrics && (
          <ResourceMetricsTimespanFilter
            value={timespan}
            onChange={onTimespanChange}
            id="action-combined-metrics-timespan"
            className="drawer-section__timespan"
          />
        )}
      </div>
      {canFetchLiveMetrics && (
        <p className="text-muted text-sm drawer-section__period-note">
          Utilization metrics reflect {metricTimespanLabel(timespan).toLowerCase()}
          {liveMetricsFetching ? ' (refreshing…)' : ''}.
        </p>
      )}

      {showSignals && (
        <div className="drawer-investigation drawer-investigation--signals">
          <h4 className="drawer-investigation__title">Merged signals</h4>
          <ActionEvidenceSignals summary={summary} />
          {(combined.unified_monthly_savings > 0
            || combined.finding_monthly_savings > 0
            || combined.advisor_monthly_savings > 0) && (
            <div className="action-combined-savings">
              {combined.unified_monthly_savings > 0 ? (
                <span>
                  Unified savings {formatCurrency(combined.unified_monthly_savings, { currency })}/mo
                </span>
              ) : combined.finding_monthly_savings > 0 ? (
                <span>
                  Engine savings {formatCurrency(combined.finding_monthly_savings, { currency })}/mo
                </span>
              ) : null}
              {combined.advisor_monthly_savings > 0 && (
                <span>Advisor reference {formatCurrency(combined.advisor_monthly_savings, { currency })}/mo</span>
              )}
              {combined.finding_monthly_savings > 0 && combined.unified_monthly_savings > 0
                && combined.finding_monthly_savings !== combined.unified_monthly_savings && (
                <span>Engine computed {formatCurrency(combined.finding_monthly_savings, { currency })}/mo</span>
              )}
              {combined.savings_by_action_class && Object.entries(combined.savings_by_action_class).map(([cls, amount]) => (
                <span key={cls}>
                  {cls.replace(/_/g, ' ')} {formatCurrency(amount, { currency })}/mo
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {tier && !compact && (
        <div className="drawer-investigation-field">
          <span className="drawer-investigation-label">Tier:</span>
          <span className={`tier-pill tier-pill--${tierTone(tier)}`}>{tierLabel(tier)}</span>
        </div>
      )}

      <div className="drawer-investigation">
        <h4 className="drawer-investigation__title">Cost</h4>
        {comparisonDays && (
          <div className="drawer-investigation-field">
            <span className="drawer-investigation-label">Comparison window:</span>
            <span>Last {comparisonDays} days vs prior {comparisonDays} days</span>
          </div>
        )}
        {cost.current_monthly_cost != null && (
          <div className="drawer-investigation-field">
            <span className="drawer-investigation-label">Current monthly cost:</span>
            <span>{formatCurrency(cost.current_monthly_cost, { currency })}</span>
          </div>
        )}
        {cost.estimated_monthly_savings > 0 && (
          <div className="drawer-investigation-field">
            <span className="drawer-investigation-label">Est. savings:</span>
            <span className="text-highlight">
              {formatCurrency(cost.estimated_monthly_savings, { currency })}
            </span>
          </div>
        )}
        {cost.savings_confidence != null && (
          <div className="drawer-investigation-field">
            <span className="drawer-investigation-label">Savings confidence:</span>
            <span>{Math.round(cost.savings_confidence)}%</span>
          </div>
        )}
        {cost.payback_months != null && (
          <div className="drawer-investigation-field">
            <span className="drawer-investigation-label">Payback:</span>
            <span>{cost.payback_months} mo</span>
          </div>
        )}
        {cost.implementation_effort && (
          <div className="drawer-investigation-field">
            <span className="drawer-investigation-label">Effort:</span>
            <span>{cost.implementation_effort}</span>
          </div>
        )}
      </div>

      {Object.keys(dimensions).length > 0 && (
        <div className="drawer-investigation">
          <h4 className="drawer-investigation__title">Score dimensions</h4>
          <div className="action-analysis-dimensions">
            <DimensionRow label="Cost" value={dimensions.cost} />
            <DimensionRow label="Safety" value={dimensions.safety} />
            <DimensionRow label="Effort" value={dimensions.effort} />
            <DimensionRow label="Workload" value={dimensions.workload} />
            <DimensionRow label="Business" value={dimensions.business} />
          </div>
        </div>
      )}

      {workload.workload_type && (
        <div className="drawer-investigation">
          <h4 className="drawer-investigation__title">Workload</h4>
          <div className="drawer-investigation-field">
            <span className="drawer-investigation-label">Type:</span>
            <span>{workload.workload_type}</span>
          </div>
          {workload.utilization_trend && (
            <div className="drawer-investigation-field">
              <span className="drawer-investigation-label">Trend:</span>
              <span>{workload.utilization_trend}</span>
            </div>
          )}
        </div>
      )}

      <MetricsTable title="Cost metrics" metrics={metrics?.cost} />
      <MetricsTable title="Utilization metrics" metrics={performanceMetrics} />

      {dataQuality && (
        <p className="text-muted text-sm">
          Data: {optimizationDataQualityLabel(dataQuality)}
        </p>
      )}

      {(utilization.performance_risk_score != null || action.performance_risk) && (
        <div className="drawer-investigation">
          <h4 className="drawer-investigation__title">Risk</h4>
          {utilization.performance_risk_score != null && (
            <div className="drawer-investigation-field">
              <span className="drawer-investigation-label">Performance risk:</span>
              <span>{Math.round(utilization.performance_risk_score)}</span>
            </div>
          )}
          {action.performance_risk && (
            <div className="drawer-investigation-field">
              <span className="drawer-investigation-label">Risk level:</span>
              <span>{action.performance_risk}</span>
            </div>
          )}
        </div>
      )}

      {rules.length > 0 && (
        <div className="drawer-investigation">
          <h4 className="drawer-investigation__title">Signals applied</h4>
          <ul className="drawer-rules-list">
            {rules.map((rule) => (
              <li key={rule} className="drawer-rules-item">{rule}</li>
            ))}
          </ul>
        </div>
      )}

      {!hasContent && (
        <p className="text-muted text-sm">Run engine scoring to refresh combined analysis for this action.</p>
      )}
    </section>
  );
}

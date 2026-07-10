import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, XCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { fetchResourceAzureMetrics } from '../api/azure';
import { toDisplayText } from '../utils/formatDisplay';
import {
  normalizeEvidence,
  evidenceTechnicalChecks,
  evidenceSavingsMethodology,
  formatEvidenceLabel,
  evidenceDataSourceLabel,
  extractResourceTechnicalDetails,
  evidenceOptimizationMetrics,
  evidenceCostSummary,
  extractRetailPricing,
  formatUsdAmount,
  optimizationMetricStatusLabel,
  optimizationDataQualityLabel,
  filterPerformanceMetricsForContext,
  dedupeChecksAgainstMetrics,
  extractAiInsight,
  formatAiRiskLabel,
  filterDrawerResourceDetails,
  isPercentOptimizationMetric,
  parseOptimizationPercentValue,
} from '../utils/evidenceUtils';
import { Sparkles } from 'lucide-react';
import AiImplementationSteps from './AiImplementationSteps';
import ArmResourceLink from './ArmResourceLink';
import { isArmResourceId } from '../utils/armResourceLinks';
import { metricTimespanLabel } from '../utils/metricsTimespanUtils';
import { liveMetricsToEvidencePerformance } from '../utils/resourceMetricsUtils';
import usePersistedMetricTimespan from '../hooks/usePersistedMetricTimespan';
import ResourceMetricsTimespanFilter from './ResourceMetricsTimespanFilter';

const EVIDENCE_METRICS_TIMESPAN_KEY = 'finops-evidence-metrics-timespan';

function EvidenceValue({ value, linkValue }) {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'object') return JSON.stringify(value);
  const text = String(value);
  const linkTarget = [linkValue, text].find((candidate) => (
    typeof candidate === 'string' && isArmResourceId(candidate)
  ));
  if (linkTarget) {
    return <ArmResourceLink resourceId={linkTarget} />;
  }
  return text;
}

function CheckStatus({ passed, status, label }) {
  if (status === 'na') {
    return (
      <span className="check-chip check-chip--na">
        Not in sync
      </span>
    );
  }
  return (
    <span className={`check-chip check-chip--${passed ? 'pass' : 'fail'}`}>
      {passed ? <CheckCircle2 size={11} aria-hidden /> : <XCircle size={11} aria-hidden />}
      {label || (passed ? 'Met' : 'Not met')}
    </span>
  );
}

function metricBarColor(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return 'var(--text3)';
  if (n >= 80) return 'var(--danger)';
  if (n >= 50) return 'var(--warning)';
  return 'var(--success)';
}

function EvidenceMetricPlain({ label, formatted, value }) {
  const raw = formatted ?? value;
  if (raw == null || raw === '' || raw === '—') return null;
  return (
    <div className="evidence-metric evidence-metric--plain">
      <span className="evidence-metric__label">{label}</span>
      <span className="evidence-metric__value">
        <EvidenceValue value={raw} linkValue={value} />
      </span>
    </div>
  );
}

function EvidenceMetricBar({ label, value, formatted }) {
  const pct = parseOptimizationPercentValue(formatted, value);
  if (pct == null || pct > 100) return null;
  return (
    <div className="evidence-metric">
      <span className="evidence-metric__label">{label}</span>
      <div className="evidence-metric__bar-track">
        <div
          className="evidence-metric__bar-fill"
          style={{ width: `${Math.min(100, pct)}%`, background: metricBarColor(pct) }}
        />
      </div>
      <span className="evidence-metric__value">{formatted ?? `${pct}%`}</span>
    </div>
  );
}

function PerformanceMetricsPanel({ metrics, timespan, onTimespanChange, resourceId, isRefreshing }) {
  if (!metrics?.length) return null;
  const periodLabel = metricTimespanLabel(timespan);
  return (
    <div className="finding-evidence__metric-bars">
      <div className="finding-evidence__metrics-toolbar">
        <div className="finding-evidence__section-label">Key metrics · {periodLabel}</div>
        {resourceId && (
          <ResourceMetricsTimespanFilter
            id="finding-evidence-metrics-timespan"
            value={timespan}
            onChange={onTimespanChange}
          />
        )}
      </div>
      {isRefreshing && (
        <p className="finding-evidence__metrics-refresh text-muted">Refreshing metrics…</p>
      )}
      {metrics.map((metric) => {
        const label = toDisplayText(metric.label);
        const pct = isPercentOptimizationMetric(metric)
          ? parseOptimizationPercentValue(metric.formatted, metric.value)
          : null;
        if (pct != null && pct <= 100) {
          return (
            <EvidenceMetricBar
              key={metric.id || metric.label}
              label={label}
              value={metric.value}
              formatted={metric.formatted}
            />
          );
        }
        return (
          <EvidenceMetricPlain
            key={metric.id || metric.label}
            label={label}
            value={metric.value}
            formatted={metric.formatted}
          />
        );
      })}
    </div>
  );
}

function MetricStatus({ status }) {
  if (!status) {
    return <span className="finding-evidence__metric-status finding-evidence__metric-status--muted">—</span>;
  }
  const label = optimizationMetricStatusLabel(status);
  const mod = status === 'healthy' || status === 'informational'
    ? (status === 'informational' ? 'muted' : 'pass')
    : status === 'unavailable'
      ? 'muted'
      : 'fail';
  return (
    <span className={`finding-evidence__metric-status finding-evidence__metric-status--${mod}`}>
      {label}
    </span>
  );
}

function OptimizationMetricsTable({ title, metrics }) {
  if (!metrics?.length) return null;
  return (
    <div className="finding-evidence__table-wrap">
      <div className="finding-evidence__section-label">{title}</div>
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
              <td>{toDisplayText(metric.label)}</td>
              <td><EvidenceValue value={metric.formatted ?? metric.value} linkValue={metric.value} /></td>
              <td><MetricStatus status={metric.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AiInsightPanel({ insight, hidePrimary = false }) {
  if (!insight) return null;
  const {
    executiveSummary,
    recommendation,
    implementationSteps,
    riskLevel,
    staleLikelihood,
    dataGaps,
  } = insight;
  const riskLabel = formatAiRiskLabel(riskLevel);
  const hasContent = (!hidePrimary && (executiveSummary || recommendation))
    || implementationSteps.length > 0
    || (staleLikelihood && staleLikelihood !== 'unknown')
    || dataGaps.length > 0;
  if (!hasContent) return null;

  return (
    <div className="finding-evidence__ai ai-insight-callout">
      <div className="finding-evidence__ai-header">
        <Sparkles size={14} aria-hidden />
        <span>AI analysis</span>
        {riskLabel && (
          <span className={`finding-evidence__ai-risk finding-evidence__ai-risk--${riskLevel}`}>
            {riskLabel}
          </span>
        )}
      </div>
      {executiveSummary && !hidePrimary && (
        <p className="finding-evidence__ai-summary">{toDisplayText(executiveSummary)}</p>
      )}
      {recommendation && !hidePrimary && (
        <p className="finding-evidence__ai-rec">{toDisplayText(recommendation)}</p>
      )}
      {implementationSteps.length > 0 && (
        <AiImplementationSteps
          steps={implementationSteps}
          className="finding-evidence__ai-steps-wrap"
        />
      )}
      {(staleLikelihood || dataGaps.length > 0) && (
        <p className="finding-evidence__ai-meta">
          {staleLikelihood && staleLikelihood !== 'unknown' && (
            <span>Stale likelihood: {formatEvidenceLabel(staleLikelihood)}</span>
          )}
          {staleLikelihood && staleLikelihood !== 'unknown' && dataGaps.length > 0 && ' · '}
          {dataGaps.length > 0 && (
            <span>Data gaps: {dataGaps.map((g) => toDisplayText(g)).join('; ')}</span>
          )}
        </p>
      )}
    </div>
  );
}

export default function FindingEvidence({ evidence: rawEvidence, context = {} }) {
  const [showDetails, setShowDetails] = useState(false);
  const [timespan, onTimespanChange] = usePersistedMetricTimespan(EVIDENCE_METRICS_TIMESPAN_KEY);
  const evidence = normalizeEvidence(rawEvidence);
  const hasEvidence = !!(evidence && Object.keys(evidence).length > 0);

  const {
    hideSummary = false,
    hideEstimatedSavings = false,
    hideEngineScores = true,
    hideContext = false,
    hideChecksWhenMetricsPresent = true,
    inventoryContext = null,
    hideAiPrimary = false,
    hideSignalsTable = false,
    resourceId = '',
  } = context;

  const metricOptions = { hideEngineScores, hideEstimatedSavings };
  const hideCostBlock = !!inventoryContext;
  const optimizationMetrics = hasEvidence
    ? evidenceOptimizationMetrics(evidence, metricOptions)
    : null;
  const costSummary = hasEvidence ? evidenceCostSummary(evidence, metricOptions) : null;
  const hasMetricSection = !!(optimizationMetrics && (
    optimizationMetrics.performance?.length > 0
    || (costSummary?.length > 0 && !hideCostBlock)
  ));
  const { data: liveMetrics, isFetching: liveMetricsFetching } = useQuery({
    queryKey: ['resource-azure-metrics', resourceId, timespan],
    queryFn: () => fetchResourceAzureMetrics({ resource_id: resourceId, timespan }),
    enabled: hasEvidence && !!resourceId && !!timespan && hasMetricSection,
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const livePerformanceMetrics = useMemo(
    () => liveMetricsToEvidencePerformance(liveMetrics),
    [liveMetrics],
  );

  if (!hasEvidence) {
    return null;
  }

  const {
    summary,
    determination,
    data_source: dataSource,
  } = evidence;

  const checks = evidenceTechnicalChecks(evidence);
  const savingsMethodology = evidenceSavingsMethodology(evidence);
  const resourceDetails = filterDrawerResourceDetails(
    extractResourceTechnicalDetails(evidence),
    inventoryContext,
  );
  const evidencePerformanceMetrics = filterPerformanceMetricsForContext(
    optimizationMetrics?.performance,
    inventoryContext,
  );
  const performanceMetrics = resourceId && livePerformanceMetrics.length
    ? filterPerformanceMetricsForContext(livePerformanceMetrics, inventoryContext)
    : evidencePerformanceMetrics;
  const visibleChecks = hideChecksWhenMetricsPresent
    ? dedupeChecksAgainstMetrics(checks, performanceMetrics)
    : checks;
  const dataSourceLabel = evidenceDataSourceLabel(dataSource);
  const determinationLabel = formatEvidenceLabel(determination);
  const summaryText = toDisplayText(summary);
  const dataQualityLabel = optimizationMetrics?.dataQuality
    ? optimizationDataQualityLabel(optimizationMetrics.dataQuality)
    : '';
  const aiInsight = extractAiInsight(evidence);
  const retailPricing = extractRetailPricing(evidence);
  const showRetailMethodology = savingsMethodology?.method === 'azure_retail_sku_diff';

  return (
    <div className="finding-evidence">
      {aiInsight && <AiInsightPanel insight={aiInsight} hidePrimary={hideAiPrimary} />}

      {summaryText && summaryText !== '—' && !hideSummary && (
        <p className="finding-evidence__summary">{summaryText}</p>
      )}

      {(dataSourceLabel || determinationLabel) && !hideContext && (
        <p className="finding-evidence__context">
          {dataSourceLabel && <span>Based on: {dataSourceLabel}</span>}
          {dataSourceLabel && determinationLabel && ' · '}
          {determinationLabel && <span>Determination: {determinationLabel}</span>}
        </p>
      )}

      {optimizationMetrics && (performanceMetrics.length > 0 || (costSummary?.length > 0 && !hideCostBlock)) && (
        <div className="finding-evidence__optimization-metrics">
          {dataQualityLabel && !hideContext && (
            <p className="finding-evidence__context finding-evidence__metrics-quality">
              Metric coverage: {dataQualityLabel}
            </p>
          )}
          <PerformanceMetricsPanel
            metrics={performanceMetrics}
            timespan={timespan}
            onTimespanChange={onTimespanChange}
            resourceId={resourceId}
            isRefreshing={!!resourceId && liveMetricsFetching && !liveMetrics}
          />
          {costSummary?.length > 0 && !hideCostBlock && (
            <OptimizationMetricsTable title="Cost summary" metrics={costSummary} />
          )}
        </div>
      )}

      {Array.isArray(evidence.trigger_metrics) && evidence.trigger_metrics.length > 0 && (
        <div className="finding-evidence__trigger-metrics">
          <div className="finding-evidence__section-label">Trigger metrics</div>
          <ul className="finding-evidence__trigger-list">
            {evidence.trigger_metrics.map((item) => (
              <li key={item.fact_key}>
                <strong>{item.label}</strong>
                {item.value != null && item.value !== '' && (
                  <> · observed: <EvidenceValue value={item.value} /></>
                )}
                {item.threshold && <> · threshold: {item.threshold}</>}
                {item.effect_cost && (
                  <p className="finding-evidence__trigger-effect">Cost: {item.effect_cost}</p>
                )}
                {item.effect_performance && (
                  <p className="finding-evidence__trigger-effect">Performance: {item.effect_performance}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {retailPricing && (
        <div className="finding-evidence__savings">
          <strong>Azure retail pricing</strong>
          <dl className="finding-evidence__meta finding-evidence__resource-details">
            {retailPricing.currentMonthlyUsd != null && (
              <>
                <dt>Current SKU (list price)</dt>
                <dd>{formatUsdAmount(retailPricing.currentMonthlyUsd)}/mo</dd>
              </>
            )}
            {retailPricing.suggestedMonthlyUsd != null && (
              <>
                <dt>Suggested SKU (list price)</dt>
                <dd>{formatUsdAmount(retailPricing.suggestedMonthlyUsd)}/mo</dd>
              </>
            )}
            {retailPricing.savingsUsd != null && (
              <>
                <dt>Est. savings</dt>
                <dd>{formatUsdAmount(retailPricing.savingsUsd)}/mo</dd>
              </>
            )}
          </dl>
          {retailPricing.pricingStatus === 'unavailable' && (
            <p className="finding-evidence__formula">Retail pricing unavailable for this SKU pair.</p>
          )}
          <p className="finding-evidence__formula">
            List/on-demand prices from Azure. Your bill may differ with discounts or reservations.
          </p>
        </div>
      )}

      {visibleChecks.length > 0 && (
        <div className="finding-evidence__table-wrap">
          <div className="finding-evidence__section-label">Technical signals</div>
          <div className="finding-evidence__check-chips">
            {visibleChecks.map((check, idx) => (
              <CheckStatus
                key={`${check?.signal || 'check'}-${idx}`}
                passed={!!check?.passed}
                status={check?.status}
                label={toDisplayText(check?.signal)}
              />
            ))}
          </div>
          {!hideSignalsTable && !inventoryContext && (
            <table className="finding-evidence__table">
              <thead>
                <tr>
                  <th scope="col">Signal</th>
                  <th scope="col">Observed</th>
                  <th scope="col">Criterion</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {visibleChecks.map((check, idx) => (
                  <tr key={`${check?.signal || 'check'}-${idx}`}>
                    <td>{toDisplayText(check?.signal)}</td>
                    <td><EvidenceValue value={check?.value} /></td>
                    <td><EvidenceValue value={check?.threshold} /></td>
                    <td><CheckStatus passed={!!check?.passed} status={check?.status} label={toDisplayText(check?.signal)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {savingsMethodology?.description && (!costSummary?.length || showRetailMethodology) && (
        <div className="finding-evidence__savings">
          <strong>How savings are estimated</strong>
          <p>{savingsMethodology.description}</p>
          {savingsMethodology.formula && (
            <p className="finding-evidence__formula">{savingsMethodology.formula}</p>
          )}
        </div>
      )}

      {resourceDetails.length > 0 && (
        <>
          <button
            type="button"
            className="finding-evidence__raw-toggle btn btn-ghost btn-sm"
            onClick={() => setShowDetails((v) => !v)}
            aria-expanded={showDetails}
          >
            {showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {showDetails ? 'Hide resource technical details' : 'Show resource technical details'}
          </button>

          {showDetails && (
            <dl className="finding-evidence__meta finding-evidence__resource-details">
              {resourceDetails.map(({ key, label, value }) => (
                <React.Fragment key={key}>
                  <dt>{label}</dt>
                  <dd><EvidenceValue value={value} /></dd>
                </React.Fragment>
              ))}
            </dl>
          )}
        </>
      )}
    </div>
  );
}

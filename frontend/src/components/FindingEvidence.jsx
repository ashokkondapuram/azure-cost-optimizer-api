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
  filterDrawerResourceDetails,
  isPercentOptimizationMetric,
  parseOptimizationPercentValue,
} from '../utils/evidenceUtils';
import ArmResourceLink from './ArmResourceLink';
import { isArmResourceId } from '../utils/armResourceLinks';
import { formatEvidenceCheckValue, formatEvidenceThreshold } from '../utils/serviceDisplayUtils';
import {
  extractRegionMigration,
  groupChecksByPillar,
  groupTriggerMetricsByPillar,
} from '../utils/pillarEvidence';
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

function RegionMigrationBanner({ migration }) {
  if (!migration?.recommendedRegionDisplay) return null;
  const { currentRegion, recommendedRegionDisplay, action } = migration;
  const isMigration = action === 'migrate_region' || currentRegion;
  if (!isMigration && !recommendedRegionDisplay) return null;

  return (
    <div className="finding-evidence__region-banner" role="note">
      <div className="finding-evidence__section-label">Region guidance</div>
      {currentRegion ? (
        <p className="finding-evidence__region-line">
          <span className="finding-evidence__region-from">{currentRegion}</span>
          <span className="finding-evidence__region-arrow" aria-hidden>→</span>
          <span className="finding-evidence__region-to">{recommendedRegionDisplay}</span>
        </p>
      ) : (
        <p className="finding-evidence__region-line">
          Recommended region: <strong>{recommendedRegionDisplay}</strong>
        </p>
      )}
      <p className="finding-evidence__region-note">
        Approved regions: Canada Central, Canada East. Validate DR pairing before migration.
      </p>
    </div>
  );
}

function PillarTriggerMetrics({ triggerMetrics }) {
  const groups = groupTriggerMetricsByPillar(triggerMetrics);
  if (!groups.length) return null;

  return (
    <div className="finding-evidence__pillar-groups">
      {groups.map((group) => (
        <div key={group.pillar} className="finding-evidence__pillar-group">
          <div className="finding-evidence__section-label">{group.label}</div>
          <ul className="finding-evidence__trigger-list">
            {group.items.map((item) => (
              <li key={`${group.pillar}-${item.fact_key}`}>
                <strong>{item.label}</strong>
                {item.value != null && item.value !== '' && (
                  <> · observed: <EvidenceValue value={item.value} /></>
                )}
                {item.threshold && <> · threshold: {item.threshold}</>}
                {item.pillarEffect && (
                  <p className="finding-evidence__trigger-effect">{item.pillarEffect}</p>
                )}
                {item.safety_gate && (
                  <p className="finding-evidence__trigger-effect finding-evidence__trigger-effect--muted">
                    Safety gate: {item.safety_gate}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function PillarTechnicalSignals({ checks, hideSignalsTable, inventoryContext }) {
  const groups = groupChecksByPillar(checks);
  if (!groups.length) return null;

  return (
    <div className="finding-evidence__pillar-groups">
      {groups.map((group) => (
        <div key={group.pillar} className="finding-evidence__pillar-group">
          <div className="finding-evidence__section-label">{group.label}</div>
          <div className="finding-evidence__check-chips">
            {group.checks.map((check, idx) => (
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
                {group.checks.map((check, idx) => (
                  <tr key={`${check?.signal || 'check'}-${idx}`}>
                    <td>{toDisplayText(check?.signal)}</td>
                    <td><EvidenceValue value={formatEvidenceCheckValue(check)} /></td>
                    <td><EvidenceValue value={formatEvidenceThreshold(check)} /></td>
                    <td>
                      <CheckStatus
                        passed={!!check?.passed}
                        status={check?.status}
                        label={toDisplayText(check?.signal)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
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

export default function FindingEvidence({ evidence: rawEvidence, context = {} }) {
  const {
    hideSummary = false,
    hideEstimatedSavings = false,
    hideEngineScores = true,
    hideContext = false,
    hideChecksWhenMetricsPresent = true,
    inventoryContext = null,
    hideSignalsTable = false,
    inlineResourceDetails = false,
    resourceId = '',
  } = context;

  const [showDetails, setShowDetails] = useState(inlineResourceDetails);
  const [timespan, onTimespanChange] = usePersistedMetricTimespan(EVIDENCE_METRICS_TIMESPAN_KEY);
  const evidence = normalizeEvidence(rawEvidence);
  const hasEvidence = !!(evidence && Object.keys(evidence).length > 0);

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
  const retailPricing = extractRetailPricing(evidence);
  const showRetailMethodology = savingsMethodology?.method === 'azure_retail_sku_diff';
  const regionMigration = extractRegionMigration(evidence, evidence?.what_if);
  const triggerMetrics = Array.isArray(evidence.trigger_metrics) ? evidence.trigger_metrics : [];

  return (
    <div className="finding-evidence zafin-prose">
      {summaryText && summaryText !== '—' && !hideSummary && (
        <p className="finding-evidence__summary">{summaryText}</p>
      )}

      {regionMigration && <RegionMigrationBanner migration={regionMigration} />}

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

      {triggerMetrics.length > 0 && (
        <div className="finding-evidence__trigger-metrics">
          <PillarTriggerMetrics triggerMetrics={triggerMetrics} />
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
          <PillarTechnicalSignals
            checks={visibleChecks}
            hideSignalsTable={hideSignalsTable}
            inventoryContext={inventoryContext}
          />
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
          {!inlineResourceDetails && (
            <button
              type="button"
              className="finding-evidence__raw-toggle btn btn-ghost btn-sm"
              onClick={() => setShowDetails((v) => !v)}
              aria-expanded={showDetails}
            >
              {showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {showDetails ? 'Hide resource technical details' : 'Show resource technical details'}
            </button>
          )}

          {(inlineResourceDetails || showDetails) && (
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

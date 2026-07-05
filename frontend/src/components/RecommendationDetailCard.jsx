import React from 'react';
import { StatusBadge } from './FindingBadges';
import { ChevronDown } from 'lucide-react';
import {
  Lightbulb, MapPin,
  FolderOpen, Eye, CheckCircle2, XCircle,
  AzureResourceIcon,
} from './FinOpsIcons';
import SeverityChip, { severityAccentClass } from './visual/SeverityChip';
import ChainStepper from './visual/ChainStepper';
import ScoreGauge from './visual/ScoreGauge';
import { iconForCategory, iconFromResourceId } from '../config/assetIcons';
import { formatCurrency, formatDateTime } from '../utils/format';
import { toDisplayText } from '../utils/formatDisplay';
import {
  normalizeEvidence,
  extractAiInsight,
  findingHasAiInsight,
  isDuplicateEvidenceText,
} from '../utils/evidenceUtils';
import { Sparkles } from 'lucide-react';
import FindingEvidence from './FindingEvidence';
import FindingResourceLinks from './FindingResourceLinks';
import RecommendationAiInsight from './RecommendationAiInsight';
import ActivityTimeline from './ActivityTimeline';
import { logFindingExecution } from '../api/azure';

const RULE_TYPE_LABELS = {
  VM_DISK_BOTTLENECK: 'Disk bottleneck',
  VM_NETWORK_BOTTLENECK: 'Network bottleneck',
  AKS_POOL_CONSOLIDATION: 'AKS consolidation',
  COST_SPIKE_DETECTED: 'Cost spike',
};

function CompactMeta({ finding }) {
  const f = finding;
  if (f.detected_at == null && f.waste_score == null && f.confidence_score == null) return null;
  return (
    <div className="rec-detail-card__score-row">
      {f.confidence_score != null && (
        <ScoreGauge label="Confidence" value={f.confidence_score} />
      )}
      {f.waste_score != null && (
        <ScoreGauge label="Waste" value={f.waste_score} />
      )}
      {f.detected_at && (
        <span className="rec-detail-card__detected">{formatDateTime(f.detected_at)}</span>
      )}
    </div>
  );
}

export default function RecommendationDetailCard({
  finding,
  currency = 'CAD',
  subscriptionId,
  onStatusChange,
  statusPending = false,
  allowResolve = true,
  defaultExpanded = false,
  hideSeverity = false,
  compact = false,
  showStatus = true,
  resourceTypeLabel = '',
  inventoryContext = null,
  selectable = false,
  selected = false,
  onSelectChange,
}) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const [showEvidence, setShowEvidence] = React.useState(false);
  const [executionPending, setExecutionPending] = React.useState(false);
  const f = finding;
  const evidence = normalizeEvidence(f.evidence);
  const aiInsight = extractAiInsight(evidence);
  const hasAi = findingHasAiInsight(f) || !!aiInsight;
  const hasEvidenceSummary = !!(evidence?.summary);
  const displayDetail = aiInsight?.executiveSummary
    || (!hasEvidenceSummary && f.detail && !isDuplicateEvidenceText(f.detail, evidence?.summary)
      ? f.detail
      : (!aiInsight?.executiveSummary && !hasEvidenceSummary ? f.detail : null));
  const displayRecommendation = aiInsight?.recommendation || f.recommendation;
  const isAiRecommendation = hasAi;
  const hasEvidence = f.evidence && Object.keys(evidence || {}).length > 0;
  const ruleTypeLabel = RULE_TYPE_LABELS[f.rule_id] || null;
  const workloadClass = evidence?.workload_class;
  const savingsUsd = f.estimated_savings_usd > 0;
  const previewText = aiInsight?.executiveSummary
    || displayRecommendation
    || displayDetail;

  React.useEffect(() => {
    if (expanded && hasEvidence && (hasAi || evidence?.optimization_metrics || evidence?.checks?.length)) {
      setShowEvidence(true);
    }
  }, [expanded, hasEvidence, hasAi, evidence]);

  const emitStatus = (status) => {
    if (!onStatusChange) return;
    onStatusChange({
      id: f.id,
      status,
      label: f.rule_name || f.resource_name || 'recommendation',
    });
  };

  const markApplied = async () => {
    if (!subscriptionId || executionPending) return;
    setExecutionPending(true);
    try {
      await logFindingExecution(
        f.id,
        { action_type: 'manual_apply', before_state: { status: f.status, rule_id: f.rule_id } },
        subscriptionId,
      );
    } finally {
      setExecutionPending(false);
    }
  };

  return (
    <article className={`rec-detail-card${expanded ? ' rec-detail-card--expanded' : ''}${compact ? ' rec-detail-card--compact' : ''}${hasAi ? ' rec-detail-card--ai' : ''}${selected ? ' rec-detail-card--selected' : ''} ${severityAccentClass(f.severity)}`}>
      <header className="rec-detail-card__header">
        {selectable && f.status === 'open' && (
          <label className="rec-detail-card__select" onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={selected}
              onChange={(e) => onSelectChange?.(f.id, e.target.checked)}
              aria-label={`Select ${f.rule_name}`}
            />
          </label>
        )}
        <button
          type="button"
          className="rec-detail-card__toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {!hideSeverity && (
            <SeverityChip severity={f.severity} size={12} />
          )}
          <span className="rec-detail-card__rule">{f.rule_name}</span>
          {ruleTypeLabel && (
            <span className="finding-type-badge">{ruleTypeLabel}</span>
          )}
          {workloadClass && (
            <span className="finding-workload-badge">{workloadClass}</span>
          )}
          {f.chain_id && f.chain_step && (
            <ChainStepper step={f.chain_step} total={f.chain_total} />
          )}
          {hasAi && (
            <span className="rec-detail-card__ai-badge" title="AI-enriched recommendation">
              <Sparkles size={11} aria-hidden />
              AI
            </span>
          )}
          {savingsUsd && (
            <span className={`savings-value${f.estimated_savings_usd > 500 ? ' savings-value--high' : ''}`}>
              {formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })}/mo
            </span>
          )}
          {showStatus && f.status && f.status !== 'open' && (
            <StatusBadge status={f.status} size={10} />
          )}
          <ChevronDown
            size={14}
            className={`rec-detail-card__chevron${expanded ? ' rec-detail-card__chevron--open' : ''}`}
            aria-hidden
          />
        </button>
        {f.status === 'open' && onStatusChange && (
          <div className="rec-detail-card__actions" onClick={(e) => e.stopPropagation()}>
            {subscriptionId && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                title="Mark as applied"
                disabled={executionPending}
                onClick={markApplied}
              >
                Mark applied
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-icon-only"
              title="Acknowledge"
              aria-label="Acknowledge"
              disabled={statusPending}
              onClick={() => emitStatus('acknowledged')}
            >
              <Eye size={14} />
            </button>
            {allowResolve && (
              <button
                type="button"
                className="btn btn-ghost btn-icon-only"
                title="Resolve"
                aria-label="Resolve"
                disabled={statusPending}
                onClick={() => emitStatus('resolved')}
              >
                <CheckCircle2 size={14} />
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-icon-only"
              title="Ignore"
              aria-label="Ignore"
              disabled={statusPending}
              onClick={() => emitStatus('ignored')}
            >
              <XCircle size={14} />
            </button>
          </div>
        )}
      </header>

      {!expanded && previewText && (
        <p className="rec-detail-card__preview">{toDisplayText(previewText)}</p>
      )}

      {expanded && (
        <div className="rec-detail-card__body">
          {hasAi ? (
            <RecommendationAiInsight
              insight={aiInsight}
              variant={compact ? 'compact' : 'full'}
              showRuleFallback={!!evidence?.rule_engine}
            />
          ) : (
            displayRecommendation && (
              <div className="rec-detail-card__rec">
                <Lightbulb size={13} />
                <span>{toDisplayText(displayRecommendation)}</span>
              </div>
            )
          )}

          {!hasAi && displayDetail && displayDetail !== displayRecommendation && (
            <p className="rec-detail-card__detail">{toDisplayText(displayDetail)}</p>
          )}

          {!compact && <FindingResourceLinks finding={f} className="rec-detail-card__links" />}

          <CompactMeta finding={f} />

          {f.impact && (
            <p className="rec-detail-card__impact">{toDisplayText(f.impact)}</p>
          )}

          {hasEvidence && (
            <div className="rec-detail-card__evidence-wrap">
              <button
                type="button"
                className="btn btn-ghost btn-sm rec-detail-card__evidence-toggle"
                onClick={() => setShowEvidence((v) => !v)}
                aria-expanded={showEvidence}
              >
                {showEvidence ? 'Hide analysis details' : 'Show analysis details'}
              </button>
              {showEvidence && (
                <FindingEvidence
                  evidence={f.evidence}
                  context={{
                    hideSummary: !!aiInsight?.executiveSummary,
                    hideContext: false,
                    hideEstimatedSavings: savingsUsd,
                    hideEngineScores: true,
                    hideAiPrimary: hasAi,
                    hideChecksWhenMetricsPresent: true,
                    inventoryContext,
                    resourceId: f.resource_id || '',
                  }}
                />
              )}
            </div>
          )}

          {expanded && subscriptionId && (
            <ActivityTimeline
              findingId={f.id}
              subscriptionId={subscriptionId}
              enabled={expanded}
            />
          )}
        </div>
      )}
    </article>
  );
}

export function ResourceRecommendationGroup({
  group,
  currency,
  subscriptionId,
  onStatusChange,
  statusPending,
  allowResolve = true,
  showStatus = true,
}) {
  const [expanded, setExpanded] = React.useState(false);
  const {
    resource_id: resourceId,
    resource_name: resourceName,
    resource_group: resourceGroup,
    location,
    resource_type: resourceType,
    findings,
    totalSavings,
    resource_app_href: groupAppHref,
    azure_portal_url: groupPortalUrl,
  } = group;

  const linkFinding = {
    resource_app_href: groupAppHref || findings[0]?.resource_app_href,
    azure_portal_url: groupPortalUrl || findings[0]?.azure_portal_url,
    resource_name: resourceName,
  };

  const displayName = resourceName || (resourceId || '').split('/').pop() || 'Unknown resource';
  const iconSrc = iconFromResourceId(resourceId) || iconForCategory(findings[0]?.category);

  const severityCounts = findings.reduce((acc, f) => {
    const s = (f.severity || 'INFO').toUpperCase();
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  const stateText = findings[0]?.resource_state || findings[0]?.state || '';
  const stateMod = /running|active/i.test(stateText) ? 'running'
    : /deallocated/i.test(stateText) ? 'deallocated'
    : /stopped/i.test(stateText) ? 'stopped' : 'unknown';

  const metaParts = [
    resourceGroup,
    location,
    resourceType,
  ].filter(Boolean);

  return (
    <section className={`rec-resource-group${expanded ? ' rec-resource-group--expanded' : ''}`}>
      <header className="rec-resource-group__header">
        <button
          type="button"
          className="rec-resource-group__toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          <AzureResourceIcon type={resourceType} src={iconSrc} size={20} />
          <div className="rec-resource-group__title">
            <h3>
              {displayName}
              {stateText && (
                <span className={`resource-state-badge resource-state-badge--${stateMod}`}>
                  {stateText}
                </span>
              )}
            </h3>
            {metaParts.length > 0 && (
              <p className="rec-resource-group__meta-inline">
                {resourceGroup && (
                  <span><FolderOpen size={11} aria-hidden /> {resourceGroup}</span>
                )}
                {location && (
                  <span><MapPin size={11} aria-hidden /> {location}</span>
                )}
                {resourceType && <span>{resourceType}</span>}
              </p>
            )}
          </div>
          <div className="rec-resource-group__stats">
            <div className="group-risk-row">
              {severityCounts.CRITICAL > 0 && (
                <span className="risk-chip risk-chip--critical">{severityCounts.CRITICAL} Critical</span>
              )}
              {severityCounts.HIGH > 0 && (
                <span className="risk-chip risk-chip--high">{severityCounts.HIGH} High</span>
              )}
              <span className="rec-resource-group__count">{findings.length} findings</span>
            </div>
            {totalSavings > 0 && (
              <span className="group-savings savings-value">
                {formatCurrency(totalSavings, { currency, decimals: 0 })}/mo savings
              </span>
            )}
          </div>
          <ChevronDown
            size={16}
            className={`rec-resource-group__chevron${expanded ? ' rec-resource-group__chevron--open' : ''}`}
            aria-hidden
          />
        </button>
      </header>

      {expanded && (
        <>
          <FindingResourceLinks finding={linkFinding} className="rec-resource-group__links" />
          <div className="rec-resource-group__findings">
            {findings.map((f) => (
              <RecommendationDetailCard
                key={f.id}
                finding={f}
                currency={currency}
                subscriptionId={subscriptionId}
                onStatusChange={onStatusChange}
                statusPending={statusPending}
                allowResolve={allowResolve}
                defaultExpanded={findings.length === 1}
                hideSeverity={false}
                compact
                showStatus={showStatus}
              />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

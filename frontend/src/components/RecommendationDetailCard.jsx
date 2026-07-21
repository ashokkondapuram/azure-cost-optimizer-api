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
import { pillarLabel } from '../utils/pillarEvidence';
import {
  normalizeEvidence,
  isDuplicateEvidenceText,
} from '../utils/evidenceUtils';
import FindingEvidence from './FindingEvidence';
import DrawerFindingEvidence from './DrawerFindingEvidence';
import FindingResourceLinks from './FindingResourceLinks';
import RecommendationHelpTooltip from './RecommendationHelpTooltip';
import ActivityTimeline from './ActivityTimeline';
import WhatIfScenarioPanel from './wiz/WhatIfScenarioPanel';
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
  inline = false,
  bodyOnly = false,
  drawerEvidence = false,
  resourceRow = null,
  showStatus = true,
  resourceTypeLabel = '',
  inventoryContext = null,
  monthlyResourceCost = 0,
  selectable = false,
  selected = false,
  onSelectChange,
}) {
  const [expanded, setExpanded] = React.useState(inline || bodyOnly || defaultExpanded);
  const [showEvidence, setShowEvidence] = React.useState(inline || bodyOnly);
  const [executionPending, setExecutionPending] = React.useState(false);
  const f = finding;
  const evidence = normalizeEvidence(f.evidence);
  const hasEvidenceSummary = !!(evidence?.summary);
  const displayDetail = !hasEvidenceSummary && f.detail && !isDuplicateEvidenceText(f.detail, evidence?.summary)
    ? f.detail
    : (hasEvidenceSummary ? null : f.detail);
  const displayRecommendation = f.recommendation;
  const hasEvidence = f.evidence && Object.keys(evidence || {}).length > 0;
  const whatIf = f.evidence?.what_if || null;
  const ruleTypeLabel = RULE_TYPE_LABELS[f.rule_id] || null;
  const workloadClass = evidence?.workload_class;
  const pillarBadge = pillarLabel(f.pillar || f.category || evidence?.pillar);
  const savingsUsd = f.estimated_savings_usd > 0;
  const previewText = displayRecommendation || displayDetail;

  React.useEffect(() => {
    if (inline || bodyOnly) {
      setExpanded(true);
      if (hasEvidence) setShowEvidence(true);
      return;
    }
    if (expanded && hasEvidence && (evidence?.optimization_metrics || evidence?.checks?.length)) {
      setShowEvidence(true);
    }
  }, [inline, bodyOnly, expanded, hasEvidence, evidence]);

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

  const detailBody = (
    <div className="rec-detail-card__body zafin-prose">
      {displayRecommendation && (
        <div className="rec-detail-card__rec">
          <Lightbulb size={13} />
          <span>{toDisplayText(displayRecommendation)}</span>
        </div>
      )}

      {displayDetail && displayDetail !== displayRecommendation && (
        <p className="rec-detail-card__detail">{toDisplayText(displayDetail)}</p>
      )}

      {!compact && <FindingResourceLinks finding={f} className="rec-detail-card__links" />}

      {whatIf && (
        <WhatIfScenarioPanel
          scenario={whatIf}
          currency={currency}
          monthlyCost={monthlyResourceCost}
          finding={f}
        />
      )}

      <CompactMeta finding={f} />

      {f.impact && (
        <p className="rec-detail-card__impact">{toDisplayText(f.impact)}</p>
      )}

      {hasEvidence && (
        <div className="rec-detail-card__evidence-wrap">
          {drawerEvidence ? (
            <DrawerFindingEvidence finding={f} row={resourceRow || inventoryContext} />
          ) : (
            <>
              {!inline && !bodyOnly && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm rec-detail-card__evidence-toggle"
                  onClick={() => setShowEvidence((v) => !v)}
                  aria-expanded={showEvidence}
                >
                  {showEvidence ? 'Hide analysis details' : 'Show analysis details'}
                </button>
              )}
              {showEvidence && (
                <FindingEvidence
                  evidence={f.evidence}
                  context={{
                    hideSummary: !!evidence?.summary,
                    hideContext: false,
                    hideEstimatedSavings: savingsUsd,
                    hideEngineScores: true,
                    hideChecksWhenMetricsPresent: true,
                    inlineResourceDetails: inline || bodyOnly,
                    inventoryContext,
                    resourceId: f.resource_id || '',
                  }}
                />
              )}
            </>
          )}
        </div>
      )}

      {(inline || expanded || bodyOnly) && !drawerEvidence && subscriptionId && (
        <ActivityTimeline
          findingId={f.id}
          subscriptionId={subscriptionId}
          enabled={expanded || bodyOnly}
        />
      )}
    </div>
  );

  const workflowActions = f.status === 'open' && onStatusChange ? (
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
  ) : null;

  if (bodyOnly) {
    return (
      <article className={`rec-detail-card rec-detail-card--body-only${compact ? ' rec-detail-card--compact' : ''} ${severityAccentClass(f.severity)}`}>
        {(workflowActions || (showStatus && f.status && f.status !== 'open')) && (
          <header className="rec-detail-card__header rec-detail-card__header--body-only">
            {showStatus && f.status && f.status !== 'open' && (
              <StatusBadge status={f.status} size={10} />
            )}
            {workflowActions}
          </header>
        )}
        {detailBody}
      </article>
    );
  }

  return (
    <article className={`rec-detail-card${expanded ? ' rec-detail-card--expanded' : ''}${compact ? ' rec-detail-card--compact' : ''}${inline ? ' rec-detail-card--inline' : ''}${selected ? ' rec-detail-card--selected' : ''} ${severityAccentClass(f.severity)}`}>
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
        {inline ? (
          <div className="rec-detail-card__title-row">
            {!hideSeverity && (
              <SeverityChip severity={f.severity} size={12} />
            )}
            <span className="rec-detail-card__rule">
              <RecommendationHelpTooltip
                finding={f}
                compact
                detailHint="Analysis details below"
              >
                {f.rule_name}
              </RecommendationHelpTooltip>
            </span>
            {pillarBadge && pillarBadge !== 'Other signals' && (
              <span className="finding-pillar-badge">{pillarBadge}</span>
            )}
            {ruleTypeLabel && (
              <span className="finding-type-badge">{ruleTypeLabel}</span>
            )}
            {workloadClass && (
              <span className="finding-workload-badge">{workloadClass}</span>
            )}
            {f.chain_id && f.chain_step && (
              <ChainStepper step={f.chain_step} total={f.chain_total} />
            )}
            {savingsUsd && (
              <span className={`savings-value${f.estimated_savings_usd > 500 ? ' savings-value--high' : ''}`}>
                {formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })}/mo
              </span>
            )}
            {showStatus && f.status && f.status !== 'open' && (
              <StatusBadge status={f.status} size={10} />
            )}
          </div>
        ) : (
          <button
            type="button"
            className="rec-detail-card__toggle"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {!hideSeverity && (
              <SeverityChip severity={f.severity} size={12} />
            )}
            <span className="rec-detail-card__rule">
              <RecommendationHelpTooltip
                finding={f}
                compact
                detailHint="Expand for analysis details"
              >
                {f.rule_name}
              </RecommendationHelpTooltip>
            </span>
            {pillarBadge && pillarBadge !== 'Other signals' && (
              <span className="finding-pillar-badge">{pillarBadge}</span>
            )}
            {ruleTypeLabel && (
              <span className="finding-type-badge">{ruleTypeLabel}</span>
            )}
            {workloadClass && (
              <span className="finding-workload-badge">{workloadClass}</span>
            )}
            {f.chain_id && f.chain_step && (
              <ChainStepper step={f.chain_step} total={f.chain_total} />
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
        )}
        {workflowActions}
      </header>

      {!inline && !expanded && previewText && (
        <RecommendationHelpTooltip
          finding={f}
          compact
          block
          className="rec-detail-card__preview-wrap"
          detailHint="Expand for analysis details"
        >
          <p className="rec-detail-card__preview">{toDisplayText(previewText)}</p>
        </RecommendationHelpTooltip>
      )}

      {(inline || expanded) && detailBody}
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

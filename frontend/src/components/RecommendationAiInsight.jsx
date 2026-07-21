import React from 'react';
import { Sparkles } from 'lucide-react';
import { toDisplayText } from '../utils/formatDisplay';
import { formatAiRiskLabel } from '../utils/evidenceUtils';
import AiImplementationSteps from './AiImplementationSteps';

/**
 * Surfaces Azure OpenAI enrichment from analysis — summary, steps, risk, and data gaps.
 */
export default function RecommendationAiInsight({
  insight,
  variant = 'full',
  showRuleFallback = false,
}) {
  if (!insight) return null;

  const {
    executiveSummary,
    recommendation,
    ruleRecommendation,
    ruleDetail,
    implementationSteps,
    riskLevel,
    staleLikelihood,
    dataGaps,
  } = insight;

  const riskLabel = formatAiRiskLabel(riskLevel);
  const steps = implementationSteps || [];
  const gaps = dataGaps || [];
  const compact = variant === 'compact';

  const hasPrimary = !!(executiveSummary || recommendation);
  const hasSteps = steps.length > 0;
  const hasMeta = (staleLikelihood && staleLikelihood !== 'unknown') || gaps.length > 0;
  const hasRuleFallback = showRuleFallback && !!(ruleRecommendation || ruleDetail);

  if (!hasPrimary && !hasSteps && !hasMeta && !hasRuleFallback) return null;

  return (
    <div className={`rec-ai-insight card card--flat zafin-prose${compact ? ' rec-ai-insight--compact' : ''}`}>
      <div className="rec-ai-insight__header">
        <Sparkles size={14} aria-hidden />
        <span className="text-title-small">AI analysis</span>
        {riskLabel && (
          <span className={`rec-ai-insight__risk rec-ai-insight__risk--${riskLevel}`}>
            {riskLabel}
          </span>
        )}
      </div>

      {executiveSummary && (
        <p className="rec-ai-insight__summary text-body-medium">{toDisplayText(executiveSummary)}</p>
      )}

      {recommendation && recommendation !== executiveSummary && (
        <p className="rec-ai-insight__rec text-body-medium">{toDisplayText(recommendation)}</p>
      )}

      {hasSteps && (
        <AiImplementationSteps steps={steps} className="rec-ai-insight__steps-wrap" />
      )}

      {hasMeta && (
        <p className="rec-ai-insight__meta text-caption">
          {staleLikelihood && staleLikelihood !== 'unknown' && (
            <span>Stale likelihood: {toDisplayText(staleLikelihood)}</span>
          )}
          {staleLikelihood && staleLikelihood !== 'unknown' && gaps.length > 0 && ' · '}
          {gaps.length > 0 && (
            <span>Data gaps: {gaps.map((g) => toDisplayText(g)).join('; ')}</span>
          )}
        </p>
      )}

      {hasRuleFallback && (
        <details className="rec-ai-insight__rule-fallback">
          <summary className="text-body-small">Rule engine baseline</summary>
          {ruleDetail && <p className="text-body-medium">{toDisplayText(ruleDetail)}</p>}
          {ruleRecommendation && ruleRecommendation !== ruleDetail && (
            <p className="text-body-medium">{toDisplayText(ruleRecommendation)}</p>
          )}
        </details>
      )}
    </div>
  );
}

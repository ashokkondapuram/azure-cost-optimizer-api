/** Tooltip copy for recommendation headlines. */

import { pillarLabel } from './pillarEvidence';
import { formatSeverityLabel } from './taxonomy';
import { toDisplayText } from './formatDisplay';

export function recommendationFullMessage(finding) {
  if (!finding) return '';
  const rec = String(finding.recommendation || '').trim();
  const detail = String(finding.detail || '').trim();
  const name = String(finding.rule_name || '').trim();
  const pick = [rec, detail, name].find((text) => text && !text.startsWith('metric_'));
  return toDisplayText(pick || name || '');
}

export function buildRecommendationTooltipContent(finding) {
  if (!finding) {
    return {
      message: '',
      pillar: '',
      severity: '',
      ariaLabel: 'Recommendation details',
      metaParts: [],
    };
  }

  const message = recommendationFullMessage(finding);
  const pillar = pillarLabel(finding.pillar || finding.category || finding.evidence?.pillar);
  const severity = formatSeverityLabel(finding.severity);
  const metaParts = [];

  if (pillar && pillar !== 'Other signals') metaParts.push(pillar);
  if (severity) metaParts.push(severity);

  const ariaLabel = [
    message,
    metaParts.length ? metaParts.join(' · ') : null,
  ].filter(Boolean).join('. ');

  return {
    message,
    pillar,
    severity,
    ariaLabel: ariaLabel || 'Recommendation details',
    metaParts,
  };
}

/** Filter and label findings for Action centre surfaces. */

import { toDisplayText } from './formatDisplay';

function isEmbeddedOnlyArmId(resourceId) {
  const armId = String(resourceId || '').toLowerCase();
  return armId.includes('/virtualmachinescalesets/');
}

export function isActionCentreFinding(finding) {
  if (isEmbeddedOnlyArmId(finding?.resource_id)) return false;
  const resourceType = String(finding?.resource_type || '').toLowerCase();
  if (resourceType === 'compute/vmss') return false;
  const ruleId = String(finding?.rule_id || '');
  if (ruleId.startsWith('metric_') && ruleId.includes('_missing')) return false;
  return true;
}

export function topFindingHeadline(finding) {
  if (!finding) return '—';
  const rec = toDisplayText(finding.recommendation);
  const detail = toDisplayText(finding.detail);
  const name = toDisplayText(finding.rule_name);
  const pick = [rec, detail, name].find((text) => text && text !== '—' && !text.startsWith('metric_'));
  const text = pick || name || '—';
  if (text.length <= 120) return text;
  return `${text.slice(0, 117)}…`;
}

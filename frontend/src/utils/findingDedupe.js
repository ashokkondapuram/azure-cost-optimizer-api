/**
 * Normalize ARM resource IDs to match backend `normalize_arm_id`.
 */
export function normalizeArmId(resourceId) {
  return (resourceId || '').trim().toLowerCase().replace(/\/+$/, '');
}

const COMMITMENT_RULE_CANONICAL = {
  SAVINGS_PLAN_OPPORTUNITY: 'SAVINGS_PLAN_OPPORTUNITY_EXTENDED',
  RESERVED_OPPORTUNITY: 'RESERVED_OPPORTUNITY_EXTENDED',
};

const SUBSCRIPTION_SCOPED_RULES = new Set([
  ...Object.keys(COMMITMENT_RULE_CANONICAL),
  ...Object.values(COMMITMENT_RULE_CANONICAL),
]);

function canonicalRuleId(ruleId) {
  const upper = (ruleId || '').trim().toUpperCase();
  return COMMITMENT_RULE_CANONICAL[upper] || upper;
}

function isSubscriptionScopedFinding(finding) {
  const rule = canonicalRuleId(finding?.rule_id);
  if (SUBSCRIPTION_SCOPED_RULES.has(rule)) return true;
  const scope = finding?.evidence?.scope;
  return scope === 'subscription';
}

/** Identity key for one open recommendation per resource + rule. */
export function openFindingDedupeKey(finding) {
  const sub = (finding?.subscription_id || '').trim().toLowerCase();
  const rule = canonicalRuleId(finding?.rule_id);
  if (isSubscriptionScopedFinding(finding)) {
    return `${sub}::${rule}`;
  }
  const rid = normalizeArmId(finding?.resource_id);
  return `${sub}::${rid}::${rule}`;
}

/** Keep the latest open finding per identity key. */
export function dedupeOpenFindings(findings = []) {
  const best = new Map();
  for (const finding of findings) {
    const key = openFindingDedupeKey(finding);
    const prev = best.get(key);
    if (!prev) {
      best.set(key, finding);
      continue;
    }
    const prevAt = prev.detected_at ? new Date(prev.detected_at).getTime() : 0;
    const curAt = finding.detected_at ? new Date(finding.detected_at).getTime() : 0;
    if (curAt >= prevAt) best.set(key, finding);
  }
  return [...best.values()];
}

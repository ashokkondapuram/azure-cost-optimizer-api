/** Detect persisted VM rightsizing findings for drawer de-duplication. */

const RIGHTSIZING_RULE_IDS = new Set([
  'VM_SKU_SIZING_EXTENDED',
  'VM_RIGHTSIZE_FAMILY',
  'VM_OVERSIZE',
  'VM_UNDERUTILIZED_EXTENDED',
]);

const RIGHTSIZING_ACTIONS = new Set(['downgrade', 'cross_family', 'upgrade']);

function parseEvidence(evidence) {
  if (!evidence) return {};
  if (typeof evidence === 'object') return evidence;
  try {
    return JSON.parse(evidence);
  } catch {
    return {};
  }
}

export function hasRightsizingFinding(findings = []) {
  return findings.some((f) => {
    if (RIGHTSIZING_RULE_IDS.has(f.rule_id)) return true;
    const action = parseEvidence(f.evidence)?.sizing_action;
    return RIGHTSIZING_ACTIONS.has(action);
  });
}

/** Preview live VM sizing in drawer/findings when not yet persisted to the index. */
export function mergeLiveVmSizingFindings(findings = [], sizingData) {
  if (!sizingData?.recommendation?.suggested_sku || hasRightsizingFinding(findings)) {
    return findings;
  }

  const { action, suggested_sku, reasons } = sizingData.recommendation;
  if (!RIGHTSIZING_ACTIONS.has(action)) return findings;

  return [
    ...findings,
    {
      id: 'live-vm-sizing-preview',
      rule_id: 'VM_SKU_SIZING_EXTENDED',
      rule_name: 'VM SKU sizing',
      severity: 'MEDIUM',
      detail: reasons?.[0],
      recommendation: reasons?.[0] || `Change SKU from ${sizingData.current_sku} to ${suggested_sku}`,
      estimated_savings_usd: sizingData.pricing?.estimated_monthly_savings_usd || 0,
    },
  ];
}

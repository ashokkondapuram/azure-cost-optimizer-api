/**
 * Cosmos DB — show one best recommendation per account in the UI.
 * Mirrors it_services/database_cosmosdb/engine/primary_recommendation.py.
 */

const PYTHON_TO_ASSESSMENT = {
  COSMOS_SERVERLESS: 'cosmos_serverless_candidate',
  COSMOS_AUTOSCALE_EXTENDED: 'cosmos_autoscale_candidate',
  COSMOS_RU_RIGHT_SIZING_UNDER: 'cosmos_rightsize_manual_throughput_down',
  COSMOS_RU_RIGHT_SIZING_OVER: 'cosmos_increase_throughput_or_fix_hot_partition',
  COSMOS_THROTTLING_DETECTED: 'cosmos_increase_throughput_or_fix_hot_partition',
  COSMOS_HOT_CONTAINER_DETECTED: 'cosmos_hot_partition',
};

const THROUGHPUT_DOWN = new Set([
  'COSMOS_SERVERLESS',
  'COSMOS_AUTOSCALE_EXTENDED',
  'COSMOS_RU_RIGHT_SIZING_UNDER',
  'COSMOS_PROVISIONED_EXTENDED',
  'cosmos_serverless_candidate',
  'cosmos_autoscale_candidate',
  'cosmos_rightsize_manual_throughput_down',
  'cosmos_autoscale_max_too_high',
]);

const CAPACITY_INCREASE = new Set([
  'COSMOS_RU_RIGHT_SIZING_OVER',
  'COSMOS_THROTTLING_DETECTED',
  'cosmos_increase_throughput_or_fix_hot_partition',
  'cosmos_autoscale_max_too_low',
]);

const HOT_PARTITION = new Set([
  'COSMOS_HOT_CONTAINER_DETECTED',
  'cosmos_hot_partition',
]);

const RULE_PRIORITY = {
  COSMOS_HOT_CONTAINER_DETECTED: 100,
  cosmos_hot_partition: 100,
  COSMOS_THROTTLING_DETECTED: 95,
  COSMOS_RU_RIGHT_SIZING_OVER: 90,
  cosmos_increase_throughput_or_fix_hot_partition: 90,
  cosmos_autoscale_max_too_low: 85,
};

const SEV_RANK = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0 };

function ruleKey(ruleId) {
  return String(ruleId || '').trim();
}

function isCosmosResource(resource, apiPath = '') {
  const type = String(resource?.type || '').toLowerCase();
  const path = String(apiPath || '').toLowerCase();
  return (
    path.includes('cosmosdb')
    || type.includes('documentdb')
    || type.includes('cosmos')
  );
}

function findingScore(finding) {
  const rule = ruleKey(finding.rule_id);
  const priority = RULE_PRIORITY[rule] || 0;
  const sev = SEV_RANK[String(finding.severity || 'MEDIUM').toUpperCase()] ?? 2;
  const savings = Number(finding.estimated_savings_usd) || 0;
  return [priority, sev, savings];
}

function compareFindings(a, b) {
  const sa = findingScore(a);
  const sb = findingScore(b);
  for (let i = 0; i < sa.length; i += 1) {
    if (sa[i] !== sb[i]) return sb[i] - sa[i];
  }
  return 0;
}

function suppressConflicting(findings) {
  if (findings.length <= 1) return findings;

  const present = new Set(findings.map((f) => ruleKey(f.rule_id)));
  const suppressed = new Set();

  const hasHot = [...HOT_PARTITION].some((r) => present.has(r));
  const hasThrottle = present.has('COSMOS_THROTTLING_DETECTED') || present.has('COSMOS_RU_RIGHT_SIZING_OVER');
  const hasCapacityStress = [...CAPACITY_INCREASE].some((r) => present.has(r));

  if (hasHot || hasThrottle || hasCapacityStress) {
    THROUGHPUT_DOWN.forEach((r) => suppressed.add(r));
  }

  if (hasHot) {
    ['COSMOS_RU_RIGHT_SIZING_OVER', 'COSMOS_THROTTLING_DETECTED', 'cosmos_increase_throughput_or_fix_hot_partition']
      .forEach((r) => suppressed.add(r));
  }

  const throughputCandidates = findings.filter((f) => THROUGHPUT_DOWN.has(ruleKey(f.rule_id)));
  if (throughputCandidates.length > 1) {
    const best = [...throughputCandidates].sort(compareFindings)[0];
    throughputCandidates.forEach((f) => {
      if (f !== best) suppressed.add(ruleKey(f.rule_id));
    });
  }

  const eligible = findings.filter((f) => !suppressed.has(ruleKey(f.rule_id)));
  return eligible.length ? eligible : findings;
}

/** Strip what-if from non-primary findings (defensive for legacy DB rows). */
export function stripNonPrimaryWhatIf(findings) {
  return findings.map((finding, index, all) => {
    if (all.length <= 1) return finding;
    const evidence = finding.evidence && typeof finding.evidence === 'object'
      ? { ...finding.evidence }
      : {};
    if (!evidence.primary_recommendation) {
      delete evidence.what_if;
    }
    return { ...finding, evidence };
  });
}

export function pickPrimaryCosmosFinding(findings = []) {
  if (!findings.length) return null;
  if (findings.length === 1) return findings[0];
  const eligible = suppressConflicting(findings);
  return [...eligible].sort(compareFindings)[0] || null;
}

export function pickPrimaryCosmosFindings(findings = [], resource, apiPath = '') {
  if (!findings.length || !isCosmosResource(resource, apiPath)) {
    return findings;
  }
  const primary = pickPrimaryCosmosFinding(findings);
  if (!primary) return [];
  const cleaned = stripNonPrimaryWhatIf([{
    ...primary,
    evidence: {
      ...(primary.evidence || {}),
      primary_recommendation: true,
    },
  }]);
  return cleaned;
}

export { isCosmosResource, PYTHON_TO_ASSESSMENT };

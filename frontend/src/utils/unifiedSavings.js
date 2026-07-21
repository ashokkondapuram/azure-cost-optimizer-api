/**
 * Engine-only unified savings — mirrors app/savings_aggregation.resolve_resource_savings
 * for open findings when the API map is unavailable.
 */
import { normalizeArmId } from './findingDedupe';

const DECOMMISSION_RULES = new Set([
  'VM_IDLE', 'VM_STOPPED_DEALLOCATED', 'VM_STOPPED_BILLING_EXTENDED', 'VM_ZOMBIE_CANDIDATE_EXTENDED',
  'DISK_UNATTACHED', 'DISK_UNUSED_EXTENDED', 'IP_UNASSOCIATED', 'AKS_EMPTY_POOL',
  'SNAPSHOT_STALE_EXTENDED', 'SNAPSHOT_ARCHIVE_EXTENDED', 'APP_SERVICE_IDLE_EXTENDED',
  'LOAD_BALANCER_NO_BACKEND', 'LOAD_BALANCER_IDLE_EXTENDED', 'NAT_GATEWAY_UNUSED_EXTENDED',
  'NAT_GATEWAY_IDLE_EXTENDED', 'PUBLIC_IP_UNASSOCIATED', 'PUBLIC_IP_IDLE_EXTENDED',
  'PRIVATE_ENDPOINT_ORPHAN_EXTENDED', 'PRIVATE_LINK_UNUSED_EXTENDED', 'PRIVATE_DNS_EMPTY_EXTENDED',
  'NIC_ORPHANED_EXTENDED', 'NSG_ORPHANED_EXTENDED', 'WEBAPP_STOPPED_EXTENDED',
]);

const RIGHTSIZE_RULES = new Set([
  'VM_SKU_SIZING_EXTENDED', 'VM_RIGHTSIZE_FAMILY', 'VM_UNDERUTILIZED_EXTENDED', 'VM_OVERSIZE',
  'VM_UNDERUTILIZED', 'REDIS_RIGHTSIZE_EXTENDED', 'DISK_OVERSIZE_EXTENDED',
  'DISK_CAPACITY_RIGHTSIZE_EXTENDED', 'VMSS_AUTOSCALE_TUNING_EXTENDED',
]);

const COMMITMENT_RULES = new Set([
  'VM_NO_RESERVED', 'VM_COMMITMENT_CANDIDATE', 'AKS_COMMITMENT_CANDIDATE',
  'RESERVED_INSTANCE_OPPORTUNITY', 'SAVINGS_PLAN_OPPORTUNITY',
]);

const GOVERNANCE_RULES = new Set([
  'VM_MISSING_GOVERNANCE_TAGS', 'GOVERNANCE_TAGS_EXTENDED', 'MISSING_GOVERNANCE_TAGS',
]);

function monthlySavings(finding) {
  return Math.max(0, Number(finding?.estimated_savings_usd) || 0);
}

function parseEvidence(finding) {
  const raw = finding?.evidence_json ?? finding?.evidence;
  if (raw && typeof raw === 'object') return raw;
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}

function classifyFinding(finding) {
  const ruleId = String(finding?.rule_id || '').toUpperCase();
  if (DECOMMISSION_RULES.has(ruleId)) return 'decommission';
  if (RIGHTSIZE_RULES.has(ruleId)) return 'rightsize';
  if (COMMITMENT_RULES.has(ruleId)) return 'commitment';
  if (GOVERNANCE_RULES.has(ruleId)) return 'governance';

  const evidence = parseEvidence(finding);
  const sizingAction = String(evidence.sizing_action || '').toLowerCase();
  if (['downgrade', 'cross_family', 'upgrade'].includes(sizingAction)) return 'rightsize';

  const text = [
    finding?.rule_name,
    finding?.detail,
    finding?.recommendation,
    ruleId,
  ].filter(Boolean).join(' ').toLowerCase();

  if (/\b(decommission|shutdown|delete|remove|unused|idle|orphan|unattached|zombie)\b/.test(text)) {
    return 'decommission';
  }
  if (/\b(rightsize|resize|downsize|sku|underutiliz|oversiz)\b/.test(text)) {
    return 'rightsize';
  }
  if (/\b(reserved instance|reservation|savings plan|commitment)\b/.test(text)) {
    return 'commitment';
  }

  const category = String(finding?.category || '').toUpperCase();
  if (category === 'COST' || monthlySavings(finding) > 0) return 'other_cost';
  return 'non_cost';
}

/**
 * Unified monthly savings for one resource's open findings (engine-only).
 */
export function unifiedResourceSavingsFromFindings(findings = []) {
  const byClass = new Map();

  for (const finding of findings) {
    const status = String(finding?.status || 'open').toLowerCase();
    if (!['open', 'acknowledged'].includes(status)) continue;

    const actionClass = classifyFinding(finding);
    if (actionClass === 'non_cost' || actionClass === 'governance') continue;

    const savings = monthlySavings(finding);
    const prev = byClass.get(actionClass);
    if (!prev || savings > prev) {
      byClass.set(actionClass, savings);
    }
  }

  if (byClass.has('decommission') && byClass.has('rightsize')) {
    byClass.delete('rightsize');
  }

  return [...byClass.values()].reduce((sum, value) => sum + value, 0);
}

export function buildSavingsByResourceMap(findings = [], apiMap = null) {
  const map = new Map();
  if (apiMap && typeof apiMap === 'object') {
    for (const [rid, amount] of Object.entries(apiMap)) {
      const key = normalizeArmId(rid);
      if (key && Number(amount) > 0) map.set(key, Number(amount));
    }
    if (map.size > 0) return map;
  }

  const grouped = new Map();
  for (const finding of findings) {
    const key = normalizeArmId(finding?.resource_id)
      || (finding?.id ? `finding:${finding.id}` : '');
    if (!key) continue;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(finding);
  }

  for (const [rid, list] of grouped) {
    const unified = unifiedResourceSavingsFromFindings(list);
    if (unified > 0) map.set(rid, unified);
  }
  return map;
}

export function resolveUnifiedResourceSavings({
  resourceId,
  findings = [],
  savingsByResource = null,
  analysisSavingsUsd = null,
  indexReady = false,
} = {}) {
  const key = normalizeArmId(resourceId);
  const fromMap = savingsByResource instanceof Map
    ? savingsByResource.get(key)
    : null;

  if (fromMap != null && fromMap > 0) return fromMap;
  if (indexReady && findings.length) {
    return unifiedResourceSavingsFromFindings(findings);
  }
  if (analysisSavingsUsd != null && analysisSavingsUsd > 0) {
    return Number(analysisSavingsUsd);
  }
  if (findings.length) {
    return unifiedResourceSavingsFromFindings(findings);
  }
  return 0;
}

export function sumUnifiedSavingsForFindings(findings = []) {
  const map = buildSavingsByResourceMap(findings);
  return [...map.values()].reduce((sum, value) => sum + value, 0);
}

export function subscriptionUnifiedSavings(summary) {
  if (!summary) return 0;
  return Number(
    summary.unified_savings?.unified_estimated_monthly_savings
    ?? summary.engine_unified_savings_usd
    ?? summary.total_estimated_savings_usd
    ?? summary.estimated_savings_usd
    ?? 0,
  );
}

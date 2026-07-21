/** Parse optimization action analysis payloads for unified UI rendering. */

import {
  evidenceOptimizationMetrics,
  optimizationDataQualityLabel,
  optimizationMetricStatusLabel,
} from './evidenceUtils';

const TIER_LABELS = {
  tier1_safe: 'Tier 1 — Safe',
  tier2_balanced: 'Tier 2 — Balanced',
  tier3_risky: 'Tier 3 — Risky',
  blocked: 'Blocked',
};

const TIER_TONES = {
  tier1_safe: 'success',
  tier2_balanced: 'warning',
  tier3_risky: 'danger',
  blocked: 'muted',
};

export function tierLabel(tier) {
  return TIER_LABELS[tier] || tier || '—';
}

export function tierTone(tier) {
  return TIER_TONES[tier] || 'muted';
}

function parseJsonField(value, fallback) {
  if (value == null) return fallback;
  if (typeof value === 'object') return value;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function parseActionAnalysis(action) {
  if (!action) return null;

  const cost = parseJsonField(action.cost_evidence, {});
  const utilization = parseJsonField(action.utilization_evidence, {});
  const rules = parseJsonField(action.decision_rules_applied, []);
  const metricsBlock = utilization.optimization_metrics || {};
  const metrics = evidenceOptimizationMetrics({ optimization_metrics: metricsBlock });
  const evidenceSummary = action.evidence_summary || cost.combined_evidence || null;

  return {
    cost,
    utilization,
    rules: Array.isArray(rules) ? rules : [],
    metrics,
    evidenceSummary,
    tier: action.recommendation_tier || cost.recommendation_tier,
    overallScore: action.overall_score ?? cost.overall_score,
    dimensions: utilization.dimensions || {},
    workload: utilization.workload || {},
    performanceRiskScore: utilization.performance_risk_score,
    dependencyBlastRadius: utilization.dependency_blast_radius,
    implementationEffort: cost.implementation_effort,
    automationAvailable: cost.automation_available,
    dataQuality: metricsBlock.data_quality,
  };
}

export { optimizationDataQualityLabel, optimizationMetricStatusLabel, formatUtilizationTrend } from './evidenceUtils';

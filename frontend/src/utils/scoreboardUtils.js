/** Optimization scoreboard display helpers. */

export const SCOREBOARD_LIMIT = 200;
export const SCOREBOARD_PAGE_SIZE = 50;

export const TIER_ORDER = [
  'tier1_safe',
  'tier2_balanced',
  'tier3_risky',
  'blocked',
  'maintenance_hold',
];

const TIER_LABELS = {
  tier1_safe: 'Tier 1 — Safe',
  tier2_balanced: 'Tier 2 — Balanced',
  tier3_risky: 'Tier 3 — Risky',
  blocked: 'Blocked',
  maintenance_hold: 'Maintenance hold',
};

const TIER_SHORT_LABELS = {
  tier1_safe: 'Tier 1',
  tier2_balanced: 'Tier 2',
  tier3_risky: 'Tier 3',
  blocked: 'Blocked',
  maintenance_hold: 'Hold',
};

const TIER_TONES = {
  tier1_safe: 'safe',
  tier2_balanced: 'balanced',
  tier3_risky: 'risky',
  blocked: 'blocked',
  maintenance_hold: 'hold',
};

const DIMENSION_LABELS = {
  cost: 'Cost',
  safety: 'Safety',
  effort: 'Effort',
  workload: 'Workload',
  business: 'Business',
};

const DIMENSION_SHORT_LABELS = {
  cost: 'Cost',
  safety: 'Safety',
  effort: 'Effort',
  workload: 'Load',
  business: 'Biz',
};

export function tierLabel(tier, { short = false } = {}) {
  if (!tier) return '—';
  if (short) return TIER_SHORT_LABELS[tier] || tier.replace(/_/g, ' ');
  return TIER_LABELS[tier] || tier.replace(/_/g, ' ');
}

export function tierTone(tier) {
  return TIER_TONES[tier] || 'muted';
}

export function dimensionLabel(key) {
  return DIMENSION_LABELS[key] || key;
}

export function dimensionShortLabel(key) {
  return DIMENSION_SHORT_LABELS[key] || key;
}

export function formatScore(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Math.round(Number(value));
}

export function scoreTone(value) {
  const score = Number(value);
  if (Number.isNaN(score)) return 'muted';
  if (score >= 75) return 'high';
  if (score >= 50) return 'mid';
  return 'low';
}

export function uniqueTiers(items = []) {
  return [...new Set(items.map((i) => i.recommendation_tier).filter(Boolean))].sort();
}

export function tierSummaryEntries(tierSummary = {}) {
  return TIER_ORDER
    .map((tier) => ({ tier, count: Number(tierSummary?.[tier]) || 0 }))
    .filter((entry) => entry.count > 0);
}

export function averageScore(items = []) {
  const scores = items
    .map((row) => Number(row.overall_recommendation_score))
    .filter((value) => !Number.isNaN(value));
  if (!scores.length) return null;
  return scores.reduce((sum, value) => sum + value, 0) / scores.length;
}

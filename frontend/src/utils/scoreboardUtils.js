/** Optimization scoreboard display helpers. */

export const SCOREBOARD_LIMIT = 200;

const TIER_LABELS = {
  tier1_safe: 'Tier 1 — Safe',
  tier2_balanced: 'Tier 2 — Balanced',
  tier3_risky: 'Tier 3 — Risky',
  blocked: 'Blocked',
};

const TIER_TONES = {
  tier1_safe: 'safe',
  tier2_balanced: 'balanced',
  tier3_risky: 'risky',
  blocked: 'blocked',
};

const DIMENSION_LABELS = {
  cost: 'Cost',
  safety: 'Safety',
  effort: 'Effort',
  workload: 'Workload',
  business: 'Business',
};

export function tierLabel(tier) {
  if (!tier) return '—';
  return TIER_LABELS[tier] || tier.replace(/_/g, ' ');
}

export function tierTone(tier) {
  return TIER_TONES[tier] || 'muted';
}

export function dimensionLabel(key) {
  return DIMENSION_LABELS[key] || key;
}

export function formatScore(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Math.round(Number(value));
}

export function uniqueTiers(items = []) {
  return [...new Set(items.map((i) => i.recommendation_tier).filter(Boolean))].sort();
}

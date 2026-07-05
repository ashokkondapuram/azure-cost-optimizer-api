/** Rollout stage display helpers. */

const STAGE_STATUS_LABELS = {
  proposed: 'Proposed',
  in_progress: 'In progress',
  completed: 'Completed',
  rolled_back: 'Rolled back',
};

const TIER_LABELS = {
  tier1_safe: 'Tier 1 — Safe',
  tier2_balanced: 'Tier 2 — Balanced',
  tier3_risky: 'Tier 3 — Risky',
};

export function rolloutStatusLabel(status) {
  return STAGE_STATUS_LABELS[status] || status || 'Proposed';
}

export function rolloutTierLabel(tier) {
  return TIER_LABELS[tier] || tier || '—';
}

export function observationProgress(stage) {
  const window = stage?.observation_window_days ?? 0;
  if (window <= 0) return { label: 'No observation', pct: 100 };
  const elapsed = stage?.observation_days_elapsed ?? 0;
  const pct = Math.min(100, Math.round((elapsed / window) * 100));
  return { label: `${elapsed} / ${window} days`, pct };
}

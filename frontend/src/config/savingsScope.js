/**
 * Copy explaining what each savings headline measures — keep in sync across hub and waste surfaces.
 */
export const SAVINGS_SCOPE = {
  hubOverview: {
    title: 'Unified subscription savings',
    description:
      'Open engine findings and active Advisor recommendations, deduped per resource. Excludes resolved or overlapping signals.',
  },
  hubActions: {
    title: 'Unified subscription savings',
    description:
      'Live open signals only — same rollup as Overview. Individual action rows may include workflow history and can differ from this total.',
  },
  hubScoreboard: {
    title: 'Unified subscription savings',
    description:
      'Same deduped engine + Advisor rollup used on Overview. Reflects scored resources, not the sum of every workflow action.',
  },
  hubScoreboardFiltered: {
    title: 'Filtered scoreboard savings',
    description:
      'Sum of savings on resources in your current tier, score, or search filter. Narrower than the subscription-wide unified total.',
  },
  wasteHeatmap: {
    title: 'Idle and waste savings only',
    description:
      'Idle, orphaned, and unattached resources only. Rightsizing, commitments, and other cost opportunities are not included.',
  },
};

/** Short metric subtitle lines (hero KPI sub-labels). */
export const SAVINGS_METRIC_SUB = {
  unified: 'Unified · per resource',
  waste: 'Idle & waste only',
  scoreboardFiltered: 'Current filter',
};

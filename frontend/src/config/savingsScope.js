/**
 * Copy explaining what each savings headline measures — keep in sync across hub and waste surfaces.
 */
export const SAVINGS_SCOPE = {
  actionCentre: {
    title: 'Unified subscription savings',
    description:
      'Open engine findings and active Advisor findings, deduped per resource. Excludes resolved or overlapping signals.',
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
};

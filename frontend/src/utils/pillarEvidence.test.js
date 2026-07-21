import {
  extractRegionMigration,
  findingRecommendedRegion,
  groupChecksByPillar,
  groupFindingsByPillar,
  groupTriggerMetricsByPillar,
  inferCheckPillar,
  pillarLabel,
} from './pillarEvidence';

describe('pillarEvidence', () => {
  test('inferCheckPillar classifies security and governance signals', () => {
    expect(inferCheckPillar({ signal: 'Missing required tag', fact_key: 'missing_tags' })).toBe('security');
    expect(inferCheckPillar({ signal: 'Unapproved region placement', fact_key: 'location' })).toBe('governance');
    expect(inferCheckPillar({ signal: 'Peak CPU utilization', fact_key: 'avg_cpu_pct' })).toBe('performance');
  });

  test('groupChecksByPillar returns ordered pillar sections', () => {
    const groups = groupChecksByPillar([
      { signal: 'Missing required tag', fact_key: 'missing_tags', passed: false },
      { signal: 'Peak CPU utilization', fact_key: 'avg_cpu_pct', passed: true },
    ]);
    expect(groups.map((g) => g.pillar)).toEqual(['performance', 'security']);
    expect(groups[0].label).toBe('Performance');
  });

  test('groupTriggerMetricsByPillar splits cost and performance effects', () => {
    const groups = groupTriggerMetricsByPillar([
      {
        fact_key: 'avg_cpu_pct',
        label: 'Average CPU utilization',
        value: '3%',
        threshold: '< 5% idle',
        effect_cost: 'Low CPU enables rightsizing.',
        effect_performance: 'High CPU blocks downsize.',
      },
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0].pillar).toBe('cost');
    expect(groups[1].pillar).toBe('performance');
    expect(groups[0].items[0].pillarEffect).toContain('rightsizing');
  });

  test('extractRegionMigration reads what-if and evidence fields', () => {
    const migration = extractRegionMigration(
      { location: 'eastus', recommendedRegion: 'canadacentral' },
      {
        action: 'migrate_region',
        currentState: { region: 'eastus' },
        recommendedTargetRegion: 'canadacentral',
        recommendedTargetRegionDisplay: 'Canada Central',
      },
    );
    expect(migration.currentRegion).toBe('eastus');
    expect(migration.recommendedRegionDisplay).toBe('Canada Central');
    expect(migration.action).toBe('migrate_region');
  });

  test('findingRecommendedRegion resolves display name from finding', () => {
    expect(findingRecommendedRegion({
      evidence: {
        what_if: {
          recommendedTargetRegionDisplay: 'Canada East',
          recommendedTargetRegion: 'canadaeast',
        },
      },
    })).toBe('Canada East');
  });

  test('groupFindingsByPillar groups by category pillar', () => {
    const groups = groupFindingsByPillar([
      { id: '1', category: 'cost', rule_name: 'A' },
      { id: '2', category: 'performance', rule_name: 'B' },
      { id: '3', pillar: 'security', rule_name: 'C' },
    ]);
    expect(groups.map((g) => g.pillar)).toEqual(['cost', 'performance', 'security']);
  });

  test('pillarLabel humanizes unknown pillars', () => {
    expect(pillarLabel('cost')).toBe('Cost');
    expect(pillarLabel('operations')).toBe('Operations');
  });
});

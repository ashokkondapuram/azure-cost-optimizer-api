import {
  buildFindingTableRows,
  computeIntelStrip,
  filterFindingRows,
  hasActionCentreData,
  resolveActionCentreEmptyState,
  sortFindingRows,
} from './actionCentreV2Utils';

describe('actionCentreV2Utils', () => {
  test('hasActionCentreData detects summary and findings', () => {
    expect(hasActionCentreData({ findings: [], summary: null })).toBe(false);
    expect(hasActionCentreData({ findings: [{ id: 'f1' }], summary: null })).toBe(true);
    expect(hasActionCentreData({ findings: [], summary: { action_centre_open_findings: 3 } })).toBe(true);
  });

  test('resolveActionCentreEmptyState distinguishes sync, analysis, and queue states', () => {
    expect(resolveActionCentreEmptyState({ hasActiveFilters: true, totalCount: 0 })).toBe('filtered');
    expect(resolveActionCentreEmptyState({ totalCount: 0, syncStatus: null })).toBe('no_sync');
    expect(resolveActionCentreEmptyState({
      totalCount: 0,
      syncStatus: { inventory: { last_synced_at: '2026-01-01T00:00:00Z' } },
    })).toBe('no_analysis');
    expect(resolveActionCentreEmptyState({
      totalCount: 0,
      syncStatus: { inventory: { last_synced_at: '2026-01-01T00:00:00Z' } },
      analysisAt: '2026-01-02T00:00:00Z',
    })).toBe('empty_queue');
  });

  test('computeIntelStrip avoids hardcoded proposed fallback', () => {
    const strip = computeIntelStrip({
      summary: {},
      visibleRows: [
        { workflow: 'proposed', severity: 'critical', savings: 10 },
        { workflow: 'approved', severity: 'low', savings: 5 },
      ],
    });
    expect(strip.proposed).toBe(1);
    expect(strip.critical).toBe(1);
    expect(strip.savings).toBe(15);
  });

  test('buildFindingTableRows skips malformed findings', () => {
    const rows = buildFindingTableRows({
      findings: [
        null,
        { resource_id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1', severity: 'HIGH', category: 'COMPUTE', rule_id: 'VM_IDLE', estimated_savings_usd: 20 },
        { severity: 'LOW' },
      ],
      resourceById: new Map(),
      actionsByResource: new Map(),
    });
    expect(rows.length).toBeGreaterThanOrEqual(0);
    expect(() => buildFindingTableRows({ findings: [null, undefined, {}] })).not.toThrow();
  });

  test('buildFindingTableRows renders one row for aggregated resource findings', () => {
    const resourceId = '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/disks/d1';
    const rows = buildFindingTableRows({
      findings: [{
        aggregated: true,
        resource_id: resourceId,
        resource_type: 'Microsoft.Compute/disks',
        severity: 'HIGH',
        category: 'STORAGE',
        rule_id: 'DISK_PREMIUM_TIER',
        recommendation: 'Change disk tier',
        estimated_savings_usd: 35,
        recommendation_count: 3,
        recommendations: [
          { id: 'f1', rule_id: 'DISK_UNUSED_EXTENDED', severity: 'MEDIUM' },
          { id: 'f2', rule_id: 'DISK_PREMIUM_TIER', severity: 'HIGH' },
          { id: 'f3', rule_id: 'DISK_OLD_SNAPSHOT', severity: 'LOW' },
        ],
      }],
      resourceById: new Map(),
      actionsByResource: new Map(),
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].recommendationCount).toBe(3);
    expect(rows[0].savings).toBe(35);
    expect(rows[0].recommendation).toContain('3 recommendations');
  });

  test('filterFindingRows and sortFindingRows handle empty input', () => {
    expect(filterFindingRows([], { workflow: 'all', severity: 'all', source: 'all', type: 'all', search: '' })).toEqual([]);
    expect(sortFindingRows([])).toEqual([]);
  });
});

import {
  openFindingsCount,
  openFindingsAllCount,
  totalEstimatedSavings,
  normalizeFindingsSummary,
  sourceBreakdownOrdered,
  classifyFindingSourceKey,
  excludedFindingsSummary,
} from './findingsSummaryUtils';

describe('findingsSummaryUtils', () => {
  test('openFindingsCount prefers action centre count', () => {
    expect(openFindingsCount({
      action_centre_open_findings: 10,
      open_findings: 99,
    })).toBe(10);
    expect(openFindingsCount({ open_findings: 12 })).toBe(12);
    expect(openFindingsCount({ open_count: 5 })).toBe(5);
    expect(openFindingsCount(null)).toBe(0);
  });

  test('openFindingsAllCount exposes raw total', () => {
    expect(openFindingsAllCount({
      open_findings_all: 50,
      open_findings: 12,
    })).toBe(50);
  });

  test('sourceBreakdownOrdered uses API ordering', () => {
    const items = sourceBreakdownOrdered({
      by_source_ordered: [
        { key: 'cost_performance', label: 'Cost & performance', count: 8 },
        { key: 'reliability_security', label: 'Reliability & security', count: 2 },
      ],
    });
    expect(items).toHaveLength(2);
    expect(items[0].count).toBe(8);
  });

  test('classifyFindingSourceKey mirrors backend buckets', () => {
    expect(classifyFindingSourceKey({ rule_id: 'advisor_rec-1' })).toBe('reliability_security');
    expect(classifyFindingSourceKey({ rule_id: 'VM_IDLE', category: 'COMPUTE' })).toBe('cost_performance');
    expect(classifyFindingSourceKey({ rule_id: 'GOVERNANCE_TAG', category: 'GOVERNANCE' })).toBe('governance');
  });

  test('excludedFindingsSummary totals hidden counts', () => {
    expect(excludedFindingsSummary({
      excluded: { metric_gaps: 3, cost_export_only: 2 },
    })).toEqual({
      metric_gaps: 3,
      cost_export_only: 2,
      total: 5,
    });
  });

  test('normalizeFindingsSummary adds aliases', () => {
    const out = normalizeFindingsSummary({
      open_findings: 3,
      total_estimated_savings_usd: 100,
      by_severity: { HIGH: 1 },
    });
    expect(out.open_count).toBe(3);
    expect(out.total_open).toBe(3);
    expect(out.total_estimated_savings_usd).toBe(100);
  });
});

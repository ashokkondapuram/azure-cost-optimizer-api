import {
  resolveResourceFindings,
  resolveDrawerResourceFindings,
  resolveResourceSavings,
  resourceHasFindings,
  countResourcesWithFindings,
  countOpenFindings,
  sumResolvedSavingsForRows,
} from './resourceFindingsUtils';

describe('resourceFindingsUtils', () => {
  const resource = {
    analysisFindingsCount: 1,
    analysisTopSeverity: 'MEDIUM',
    analysisSavingsUsd: 42,
    analysisSummary: [
      {
        rule_id: 'DISK_UNATTACHED',
        rule_name: 'Unattached disk',
        severity: 'HIGH',
        recommendation: 'Delete or attach the disk',
        estimated_savings_usd: 42,
      },
    ],
  };

  it('prefers index findings when present', () => {
    const index = [{ id: 'f1', severity: 'CRITICAL', estimated_savings_usd: 10 }];
    expect(resolveResourceFindings(resource, index)).toEqual(index);
  });

  it('falls back to analysisSummary when index is empty', () => {
    const findings = resolveResourceFindings(resource, []);
    expect(findings).toHaveLength(1);
    expect(findings[0].rule_id).toBe('DISK_UNATTACHED');
    expect(findings[0].severity).toBe('HIGH');
  });

  it('falls back to analysisSummary when index is ready but empty for resource', () => {
    const findings = resolveResourceFindings(resource, [], { indexReady: true });
    expect(findings).toHaveLength(1);
    expect(findings[0].rule_id).toBe('DISK_UNATTACHED');
    expect(resourceHasFindings(resource, [], { indexReady: true })).toBe(true);
  });

  it('returns empty when index is ready, empty, and row has no analysis metadata', () => {
    expect(resolveResourceFindings({}, [], { indexReady: true })).toEqual([]);
    expect(resourceHasFindings({}, [], { indexReady: true })).toBe(false);
  });

  it('falls back to analysisFindingsCount when summary is empty', () => {
    const row = {
      analysisFindingsCount: 2,
      analysisTopSeverity: 'HIGH',
      analysisSavingsUsd: 15,
      analysisSummary: [],
    };
    const findings = resolveResourceFindings(row, []);
    expect(findings).toHaveLength(2);
    expect(findings[0].severity).toBe('HIGH');
  });

  it('resolves savings from row when index is empty', () => {
    expect(resolveResourceSavings(resource, [])).toBe(42);
  });

  it('detects findings from either source', () => {
    expect(resourceHasFindings(resource, [])).toBe(true);
    expect(resourceHasFindings({}, [])).toBe(false);
  });

  it('uses count fallback when summary is truncated vs analysisFindingsCount', () => {
    const row = {
      analysisFindingsCount: 8,
      analysisTopSeverity: 'HIGH',
      analysisSavingsUsd: 100,
      analysisSummary: [
        { rule_id: 'A', severity: 'HIGH', estimated_savings_usd: 10 },
        { rule_id: 'B', severity: 'MEDIUM', estimated_savings_usd: 5 },
      ],
    };
    const findings = resolveResourceFindings(row, []);
    expect(findings).toHaveLength(8);
    expect(findings[0].severity).toBe('HIGH');
  });

  it('drawer resolver keeps all cosmos findings instead of collapsing to primary', () => {
    const cosmos = {
      type: 'Microsoft.DocumentDB/databaseAccounts',
      analysisSummary: [],
    };
    const index = [
      { id: 'f1', rule_id: 'COSMOS_SERVERLESS', severity: 'MEDIUM' },
      { id: 'f2', rule_id: 'COSMOS_HOT_CONTAINER_DETECTED', severity: 'HIGH' },
    ];
    expect(resolveResourceFindings(cosmos, index, { apiPath: '/resources/cosmosdb' })).toHaveLength(1);
    expect(resolveDrawerResourceFindings(cosmos, index)).toHaveLength(2);
  });

  it('aggregates resource and finding counts consistently', () => {
    const rowWithSummary = { ...resource, id: '/subscriptions/x/resourcegroups/a/providers/microsoft.compute/disks/d1' };
    const rowClear = { id: '/subscriptions/x/resourcegroups/a/providers/microsoft.compute/disks/d2' };
    const rows = [rowWithSummary, rowClear];
    const rid = (row) => row.id.toLowerCase();
    const byResourceId = new Map();
    const savingsByResource = new Map();

    expect(countResourcesWithFindings(rows, byResourceId, rid)).toBe(1);
    expect(countOpenFindings(rows, byResourceId, rid)).toBe(1);
    expect(sumResolvedSavingsForRows(rows, byResourceId, savingsByResource, rid)).toBe(42);
  });
});

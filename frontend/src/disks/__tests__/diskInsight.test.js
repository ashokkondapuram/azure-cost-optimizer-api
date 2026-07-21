import { buildPropertyGroups, buildRuleEvidence } from '../diskInsight';
import { apiRowToConceptDisk } from '../diskApiModel';
import { getRuleEvidence } from '../diskAssessment';

describe('diskInsight', () => {
  test('buildPropertyGroups returns four assessment groups', () => {
    const disk = apiRowToConceptDisk({
      name: 'disk-01',
      sku: 'Premium_LRS',
      properties: {
        diskSizeGB: 128,
        diskState: 'Attached',
        diskIOPSReadWrite: 500,
        diskMBpsReadWrite: 100,
        managedBy: '/subscriptions/sub/.../virtualMachines/vm-01',
        encryption: 'EncryptionAtRestWithPlatformKey',
      },
    });

    const groups = buildPropertyGroups(disk);
    expect(groups.map((g) => g.group)).toEqual(
      expect.arrayContaining(['configuration', 'capacity', 'attachment', 'security']),
    );
    expect(groups.find((g) => g.group === 'configuration')?.items.some((i) => i.label === 'Disk size')).toBe(true);
  });

  test('buildRuleEvidence uses assessment required_evidence', () => {
    const disk = apiRowToConceptDisk({
      name: 'disk-01',
      sku: 'Premium_LRS',
      properties: { diskState: 'Unattached', lastOwnershipUpdateTime: '2024-01-01T00:00:00Z' },
      metrics: { disk_read_bps: 512, disk_write_bps: 256, disk_iops_utilization_pct: 4 },
      finding: { rule_id: 'DISK_UNUSED_EXTENDED', severity: 'high', savings: 20 },
    });

    const evidence = buildRuleEvidence(disk);
    expect(evidence.length).toBeGreaterThan(0);
    expect(evidence.every((row) => row.signal && row.value != null)).toBe(true);
    expect(evidence.every((row) => row.label && row.threshold)).toBe(true);
    expect(evidence.some((row) => row.pillar)).toBe(true);
    expect(evidence.every((row) => !String(row.label).toLowerCase().includes('assessment file'))).toBe(true);
  });

  test('buildRuleEvidence prefers API evidence_rows over raw inventory keys', () => {
    const disk = apiRowToConceptDisk({
      name: 'disk-02',
      sku: 'Premium_LRS',
      properties: { diskState: 'Attached' },
      metrics: { disk_iops_utilization_pct: 8, disk_read_bps: 400, disk_write_bps: 300 },
      finding: {
        rule_id: 'DISK_OVERSIZE_EXTENDED',
        severity: 'high',
        savings: 42,
        evidence: {
          evidence_rows: [
            {
              signal: 'disk_iops_utilization_pct',
              label: 'Disk IOPS utilization',
              value: '8%',
              threshold: '< 50%',
              period: '7d',
              pillar: 'performance',
              status: 'pass',
            },
          ],
          evidence_factors: ['Peak IOPS utilization below threshold'],
        },
      },
    });

    const evidence = buildRuleEvidence(disk);
    expect(evidence).toHaveLength(1);
    expect(evidence[0].label).toBe('Disk IOPS utilization');
    expect(evidence[0].value).toBe('8%');
    expect(evidence[0].threshold).toBe('< 50%');
  });

  test('getRuleEvidence returns required_evidence from assessment JSON', () => {
    const def = getRuleEvidence('DISK_OVERSIZE_EXTENDED');
    expect(def?.required_evidence?.length).toBeGreaterThan(0);
    expect(def.required_evidence.some((row) => row.signal === 'disk_iops_utilization_pct')).toBe(true);
    expect(def.evidence_factors?.length).toBeGreaterThan(0);
  });
});

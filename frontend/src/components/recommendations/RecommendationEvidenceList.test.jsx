import { buildRecommendationsPanelModel } from '../../utils/recommendationEvidence';

describe('RecommendationEvidenceList model', () => {
  test('three recommendations each with two evidence rows and no JSON config keys', () => {
    const items = buildRecommendationsPanelModel([
      {
        id: 'f1',
        rule_name: 'Unused disk',
        rule_id: 'DISK_UNUSED_EXTENDED',
        estimated_savings_usd: 45,
        evidence: {
          evidence_rows: [
            { label: 'Peak IOPS utilization', value: '8%', threshold: '< 30%' },
            { label: 'Unattached for', value: '45 days', threshold: '> 30 days' },
          ],
        },
      },
      {
        id: 'f2',
        rule_name: 'Premium tier over-provisioned',
        rule_id: 'DISK_OVERSIZE_EXTENDED',
        estimated_savings_usd: 20,
        evidence: {
          evidence_rows: [
            { label: 'Read throughput', value: '400 B/s', threshold: '< 1,024 B/s' },
            { label: 'Peak IOPS', value: '12% of provisioned', threshold: '< 50%' },
          ],
        },
      },
      {
        id: 'f3',
        rule_name: 'Right-size capacity',
        rule_id: 'DISK_CAPACITY_RIGHTSIZE_EXTENDED',
        estimated_savings_usd: 15,
        evidence: {
          evidence_rows: [
            { label: 'Disk size', value: '512 GB', threshold: null },
            { label: 'Used capacity', value: '48 GB', threshold: '< 30%' },
          ],
        },
      },
    ]);

    expect(items).toHaveLength(3);
    expect(items.every((item) => item.evidenceRows.length === 2)).toBe(true);

    const rendered = JSON.stringify(items);
    expect(rendered).toContain('Peak IOPS utilization');
    expect(rendered).toContain('Read throughput');
    expect(rendered).toContain('Disk size');
    expect(rendered).not.toMatch(/assessment_file|required_evidence|rule_thresholds/);
  });
});

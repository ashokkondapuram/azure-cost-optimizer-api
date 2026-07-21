import {
  buildRecommendationEvidenceRows,
  buildRecommendationsPanelModel,
  recommendationDisplayTitle,
} from './recommendationEvidence';

describe('recommendationEvidence', () => {
  test('uses structured evidence_rows without config keys', () => {
    const rows = buildRecommendationEvidenceRows({
      rule_id: 'DISK_UNUSED_EXTENDED',
      evidence: {
        evidence_rows: [
          {
            label: 'Peak IOPS utilization',
            value: '8%',
            threshold: '< 30%',
            status: 'pass',
          },
          {
            label: 'Unattached for',
            value: '45 days',
            threshold: '> 30 days',
            status: 'fail',
          },
        ],
        assessment_file: 'disk-assessment.json',
        required_evidence: [{ signal: 'disk_iops_utilization_pct' }],
      },
    });

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      label: 'Peak IOPS utilization',
      value: '8%',
      threshold: '< 30%',
    });
    expect(JSON.stringify(rows)).not.toContain('assessment_file');
  });

  test('buildRecommendationsPanelModel returns one item per finding', () => {
    const items = buildRecommendationsPanelModel([
      {
        id: 'f1',
        rule_name: 'Unused disk',
        rule_id: 'DISK_UNUSED_EXTENDED',
        estimated_savings_usd: 45,
        evidence: {
          evidence_rows: [
            { label: 'Peak IOPS utilization', value: '8%', threshold: '< 30%' },
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
          ],
        },
      },
    ]);

    expect(items).toHaveLength(2);
    expect(items[0].title).toBe('Unused disk');
    expect(items[0].evidenceRows).toHaveLength(1);
    expect(recommendationDisplayTitle({ rule_name: 'Right-size capacity' })).toBe('Right-size capacity');
  });
});

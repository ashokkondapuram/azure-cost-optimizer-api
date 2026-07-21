import {
  aggregatedRecommendationHeadline,
  expandFindingRecommendations,
  recommendationCountForFinding,
} from './findingAggregation';

describe('findingAggregation', () => {
  test('expandFindingRecommendations returns child rules for aggregated findings', () => {
    const finding = {
      aggregated: true,
      resource_id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/disks/d1',
      recommendations: [
        { id: 'f1', rule_id: 'DISK_UNUSED_EXTENDED', severity: 'HIGH' },
        { id: 'f2', rule_id: 'DISK_PREMIUM_TIER', severity: 'MEDIUM' },
      ],
    };
    expect(expandFindingRecommendations(finding)).toHaveLength(2);
    expect(expandFindingRecommendations(finding)[0].resource_id).toBe(finding.resource_id);
  });

  test('recommendationCountForFinding handles aggregated and single findings', () => {
    expect(recommendationCountForFinding({ rule_id: 'VM_IDLE' })).toBe(1);
    expect(recommendationCountForFinding({
      aggregated: true,
      recommendation_count: 3,
      recommendations: [{}, {}, {}],
    })).toBe(3);
  });

  test('aggregatedRecommendationHeadline appends recommendation count', () => {
    expect(aggregatedRecommendationHeadline({ aggregated: true, recommendation_count: 3 }, 'Resize disk'))
      .toBe('Resize disk · 3 recommendations');
    expect(aggregatedRecommendationHeadline({ rule_id: 'VM_IDLE' }, 'Stop VM')).toBe('Stop VM');
  });
});

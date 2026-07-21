import {
  buildRecommendationTooltipContent,
  recommendationFullMessage,
} from './recommendationTooltip';

describe('recommendationTooltip', () => {
  const finding = {
    rule_name: 'Disk oversize',
    recommendation: 'Downgrade to Standard SSD to reduce cost.',
    detail: 'Average IOPS utilization is below 30%.',
    pillar: 'cost',
    severity: 'HIGH',
  };

  it('prefers recommendation text for the full message', () => {
    expect(recommendationFullMessage(finding)).toBe('Downgrade to Standard SSD to reduce cost.');
  });

  it('builds tooltip meta with pillar and severity labels', () => {
    const content = buildRecommendationTooltipContent(finding);
    expect(content.message).toBe('Downgrade to Standard SSD to reduce cost.');
    expect(content.pillar).toBe('Cost');
    expect(content.severity).toBe('High');
    expect(content.metaParts).toEqual(['Cost', 'High']);
    expect(content.ariaLabel).toContain('Downgrade to Standard SSD');
    expect(content.ariaLabel).toContain('Cost');
    expect(content.ariaLabel).toContain('High');
  });

  it('omits other-signals pillar from meta', () => {
    const content = buildRecommendationTooltipContent({
      ...finding,
      pillar: 'other',
    });
    expect(content.metaParts).toEqual(['High']);
  });
});

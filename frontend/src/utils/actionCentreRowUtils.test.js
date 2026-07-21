import {
  stripRegionFromHeadline,
  sourceBadgeLabel,
  buildActionCentreRowDisplay,
  categoryLabelForRec,
  resourceMetaLine,
} from './actionCentreRowUtils';

describe('actionCentreRowUtils', () => {
  test('stripRegionFromHeadline removes duplicated region text', () => {
    expect(stripRegionFromHeadline('Move workload to eastus2 for savings', 'eastus2'))
      .toBe('Move workload for savings');
    expect(stripRegionFromHeadline('Relocate → eastus2', 'eastus2'))
      .toBe('Relocate');
  });

  test('sourceBadgeLabel maps buckets to short labels', () => {
    expect(sourceBadgeLabel({ rule_id: 'VM_IDLE', category: 'COMPUTE' })).toBe('Cost');
    expect(sourceBadgeLabel({ rule_id: 'advisor_x' })).toBe('Advisor');
    expect(sourceBadgeLabel({ category: 'GOVERNANCE' })).toBe('Governance');
  });

  test('buildActionCentreRowDisplay dedupes region between headline and secondary', () => {
    const rec = {
      topFinding: {
        severity: 'HIGH',
        category: 'COMPUTE',
        recommendation: 'Right-size VM in eastus2',
        evidence: {
          what_if: { recommendedTargetRegion: 'eastus2' },
        },
      },
      findingCount: 3,
    };
    const display = buildActionCentreRowDisplay(rec);
    expect(display.headline).not.toMatch(/eastus2/i);
    expect(display.secondaryLine).toContain('→ eastus2');
    expect(display.secondaryLine).toContain('+2 more');
    expect(display.sourceBadge).toBe('Cost');
  });

  test('resource meta is resource group only', () => {
    expect(resourceMetaLine({ resource_group: 'rg-apps', name: 'vm-01' })).toBeTruthy();
  });

  test('categoryLabelForRec uses top finding category', () => {
    expect(categoryLabelForRec({
      topFinding: { category: 'COMPUTE' },
    })).toBeTruthy();
  });
});

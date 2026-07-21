import {
  resolveActionEvidenceHighlights,
  resolveActionNarrative,
  resolveFindingPreviewText,
} from './actionNarrativeUtils';

describe('actionNarrativeUtils', () => {
  it('prefers evidence summary for finding preview text', () => {
    const text = resolveFindingPreviewText({
      recommendation: 'Downgrade disk tier',
      evidence: {
        summary: 'Attached Premium disk with near-zero I/O (512 GB, Premium_LRS).',
      },
    });
    expect(text).toContain('near-zero I/O');
    expect(text).not.toBe('Downgrade disk tier');
  });

  it('resolves action narrative from evidence-backed reason', () => {
    const narrative = resolveActionNarrative({
      action_reason: 'VM average CPU is 12.0% over the evaluation window. Resize from Standard_D4s_v3 to Standard_D2s_v3. $127/mo estimated savings',
    });
    expect(narrative).toContain('12.0%');
    expect(narrative).toContain('Standard_D2s_v3');
  });

  it('extracts narrative highlights from utilization evidence', () => {
    const highlights = resolveActionEvidenceHighlights({
      utilization_evidence: {
        narrative_highlights: [
          { label: 'Average CPU utilization', value: '12.0% (threshold: ≤ 5%)' },
          { label: 'Target SKU', value: 'Standard_D2s_v3' },
        ],
      },
    });
    expect(highlights).toHaveLength(2);
    expect(highlights[0].label).toBe('Average CPU utilization');
  });
});

import { countTriggerMetricsForFindings, findingTriggerMetrics } from './triggerUtils';

describe('triggerUtils', () => {
  it('counts unique trigger metrics from evidence', () => {
    const findings = [{
      evidence: {
        trigger_metrics: [
          { fact_key: 'avg_cpu_pct', label: 'Avg CPU' },
          { fact_key: 'avg_memory_pct', label: 'Avg memory' },
        ],
      },
    }, {
      trigger_metrics: [{ fact_key: 'avg_cpu_pct', label: 'Avg CPU' }],
    }];
    expect(countTriggerMetricsForFindings(findings)).toBe(2);
  });

  it('returns empty when no triggers', () => {
    expect(countTriggerMetricsForFindings([{ evidence: {} }])).toBe(0);
    expect(findingTriggerMetrics({})).toEqual([]);
  });
});

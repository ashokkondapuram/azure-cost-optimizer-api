import {
  formatFactValue,
  labelForFactKey,
  liveMetricsToEvidencePerformance,
  metricsSummaryRows,
} from './resourceMetricsUtils';

describe('resourceMetricsUtils', () => {
  test('formats percent and bytes', () => {
    expect(formatFactValue('avg_cpu_pct', 12.345)).toBe('12.3%');
    expect(formatFactValue('used_capacity_bytes', 5_368_709_120)).toBe('5.00 GB');
  });

  test('builds summary rows with labels', () => {
    const rows = metricsSummaryRows([
      { fact_key: 'avg_cpu_pct', label: 'Peak CPU utilization', metric_name: 'Percentage CPU', value: 8.2 },
      { fact_key: 'transaction_count', label: 'Transaction volume', metric_name: 'Transactions', value: null },
    ]);
    expect(rows[0].formatted).toBe('8.2%');
    expect(rows[0].label).toBe('Peak CPU utilization');
    expect(rows[1].formatted).toBe('—');
    expect(labelForFactKey('unknown_metric_key')).toBe('Unknown Metric Key');
  });

  test('maps live Azure Monitor payload into evidence performance metrics', () => {
    const metrics = liveMetricsToEvidencePerformance({
      ok: true,
      metrics: [{
        fact_key: 'avg_cpu_pct',
        label: 'Average CPU utilization',
        unit: 'percent',
        stats: { average: 14.2 },
        status: 'underutilized',
      }],
      derived: [],
    });
    expect(metrics).toEqual([{
      id: 'avg_cpu_pct',
      label: 'Average CPU utilization',
      value: 14.2,
      formatted: '14.2%',
      status: 'underutilized',
    }]);
    expect(liveMetricsToEvidencePerformance({ ok: false })).toEqual([]);
  });
});

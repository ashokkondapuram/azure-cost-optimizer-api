import {
  formatFactValue,
  labelForFactKey,
  liveMetricsToEvidencePerformance,
  metricsSummaryRows,
  normalizeMetricRow,
  statColumnsForRows,
} from './resourceMetricsUtils';

describe('resourceMetricsUtils', () => {
  test('formats percent and bytes', () => {
    expect(formatFactValue('avg_cpu_pct', 12.345)).toBe('12.3%');
    expect(formatFactValue('used_capacity_bytes', 5_368_709_120)).toBe('5.00 GB');
  });

  test('formats cpu time as duration not percent', () => {
    expect(formatFactValue('cpu_time_sec', 2400.8, 'seconds')).toBe('40 min');
    expect(formatFactValue('cpu_time_sec', 2400.8)).toBe('40 min');
    expect(formatFactValue('cpu_time_sec', 45, 'seconds')).toBe('45 s');
  });

  test('formats misleading byte and latency fact keys', () => {
    expect(formatFactValue('byte_count', 1_500_000_000)).toBe('1.40 GB');
    expect(formatFactValue('pe_bytes_in', 2048)).toBe('2.0 KB');
    expect(formatFactValue('query_duration_ms', 125.4)).toBe('125.4 ms');
    expect(formatFactValue('ingestion_bytes', 512)).toBe('512 MB');
    expect(formatFactValue('provisioned_throughput', 400)).toBe('400');
    expect(formatFactValue('avg_cpu_pct', 32.8)).toBe('32.8%');
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

  test('unifies stat columns across mixed metric types', () => {
    const columns = statColumnsForRows([
      {
        fact_key: 'byte_count',
        display_stats: ['total', 'average', 'maximum', 'minimum'],
        stats: { total: 1000, average: 10, maximum: 50, minimum: 1 },
      },
      {
        fact_key: 'vip_availability_pct',
        display_stats: ['average', 'minimum', 'maximum'],
        stats: { average: 99.9, maximum: 100, minimum: 98 },
      },
    ]);
    expect(columns.map((c) => c.key)).toEqual(['total', 'average', 'minimum', 'maximum']);
  });

  test('normalizes value-only cost export rows', () => {
    const row = normalizeMetricRow({
      fact_key: 'monthly_cost_usd',
      value: 42.5,
      primary_stat: 'total',
      display_stats: ['total'],
      unit: 'usd',
    });
    expect(row.stats.total).toBe(42.5);
  });
});

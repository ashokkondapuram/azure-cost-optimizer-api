import {
  buildMetricTrendChart,
  buildTrendSeriesFromMetrics,
  extractSeriesPointsFromBundle,
  mergeTrendSeriesPoints,
  trendSummaryFromSeries,
  hasTrendMetricValue,
  hasTrendMetricDataInBundle,
} from './drawerMetricTrendSeries';
import { trendMetricKeysForType } from './drawerTrendMetrics';

describe('drawerMetricTrendSeries', () => {
  const bundle = {
    metrics: [
      {
        fact_key: 'normalized_ru_pct',
        label: 'RU utilization',
        value: 0.2,
        series_points: [
          { date: '2026-07-08', value: 0.15 },
          { date: '2026-07-09', value: 0.18 },
          { date: '2026-07-10', value: 0.2 },
        ],
      },
      {
        fact_key: 'disk_read_iops',
        stats: { average: 120 },
        series_points: [
          { date: '2026-07-08', value: 100 },
          { date: '2026-07-09', value: 110 },
        ],
      },
    ],
    derived: [
      {
        fact_key: 'max_cpu_pct',
        value: 42,
        series_points: [{ date: '2026-07-10', value: 42 }],
      },
    ],
  };

  test('extractSeriesPointsFromBundle reads metrics and derived rows', () => {
    expect(extractSeriesPointsFromBundle(bundle, 'normalized_ru_pct')).toHaveLength(3);
    expect(extractSeriesPointsFromBundle(bundle, 'max_cpu_pct')).toHaveLength(1);
    expect(extractSeriesPointsFromBundle(bundle, 'missing')).toEqual([]);
  });

  test('mergeTrendSeriesPoints prefers API history when sufficient', () => {
    const api = [{ date: '2026-07-01', value: 1 }, { date: '2026-07-02', value: 2 }];
    const bundlePts = [{ date: '2026-07-08', value: 3 }];
    expect(mergeTrendSeriesPoints(api, bundlePts)).toEqual(api);
  });

  test('mergeTrendSeriesPoints falls back to bundle series', () => {
    const bundlePts = [
      { date: '2026-07-08', value: 3 },
      { date: '2026-07-09', value: 4 },
    ];
    expect(mergeTrendSeriesPoints([], bundlePts)).toEqual(bundlePts);
    expect(mergeTrendSeriesPoints([{ date: '2026-07-08', value: 1 }], bundlePts)).toEqual(bundlePts);
  });

  test('buildTrendSeriesFromMetrics builds chart rows per spec', () => {
    const specs = [
      { factKey: 'normalized_ru_pct', label: 'RU utilization', unit: '%' },
      { factKey: 'disk_read_iops', label: 'Read IOPS', unit: '' },
    ];
    const built = buildTrendSeriesFromMetrics(bundle, specs);
    expect(built).toHaveLength(2);
    expect(built[0].chartData).toHaveLength(3);
    expect(built[0].chartData[0]).toMatchObject({ value: 0.15, factKey: 'normalized_ru_pct' });
    expect(built[1].chartData).toHaveLength(2);
  });

  test('buildMetricTrendChart sorts by date ascending', () => {
    const chart = buildMetricTrendChart(
      [{ date: '2026-07-10', value: 2 }, { date: '2026-07-08', value: 1 }],
      { label: 'Test', factKey: 'avg_cpu_pct', unit: '%' },
    );
    expect(chart.map((row) => row.date)).toEqual(['2026-07-08', '2026-07-10']);
  });

  test('trendSummaryFromSeries formats latest value', () => {
    const summary = trendSummaryFromSeries(
      [{ date: '2026-07-08', value: 12.5 }, { date: '2026-07-09', value: 18 }],
      'Average CPU',
      'avg_cpu_pct',
      'Last 7 days',
    );
    expect(summary.label).toBe('Average CPU');
    expect(summary.value).toContain('18');
    expect(summary.detail).toContain('Last 7 days');
  });

  test('trendSummaryFromSeries formats pod count as integer', () => {
    const summary = trendSummaryFromSeries(
      [{ date: '2026-07-08', value: 3200 }, { date: '2026-07-09', value: 3220.23 }],
      'Ready pods',
      'pod_count',
      'Last 7 days',
    );
    expect(summary.value).toBe('3,220');
  });

  test('hasTrendMetricValue detects scalar bundle metrics', () => {
    expect(hasTrendMetricValue(bundle, 'normalized_ru_pct')).toBe(true);
    expect(hasTrendMetricValue({ facts: { avg_cpu_pct: 12.5 } }, 'avg_cpu_pct')).toBe(true);
    expect(hasTrendMetricValue(bundle, 'missing')).toBe(false);
  });

  test('hasTrendMetricDataInBundle detects cosmos RU utilization', () => {
    const specs = [{ factKey: 'normalized_ru_pct', label: 'RU utilization', unit: '%' }];
    expect(hasTrendMetricDataInBundle(bundle, specs)).toBe(true);
    expect(hasTrendMetricDataInBundle({ metrics: [] }, specs)).toBe(false);
  });

  test('extractSeriesPointsFromBundle reads metrics_detail fallback rows', () => {
    const payload = {
      metrics: [{ fact_key: 'total_ru', value: 100 }],
      metrics_detail: [{
        fact_key: 'normalized_ru_pct',
        series_points: [
          { date: '2026-07-08', value: 15 },
          { date: '2026-07-09', value: 18 },
        ],
      }],
    };
    expect(extractSeriesPointsFromBundle(payload, 'normalized_ru_pct')).toHaveLength(2);
  });

  test.each([
    ['compute/vm', 'avg_cpu_pct', 12.5],
    ['compute/disk', 'disk_read_iops', 110],
    ['containers/aks', 'cluster_cpu_pct', 38],
  ])('buildTrendSeriesFromMetrics charts %s from bundle series_points', (canonicalType, factKey, latest) => {
    const specs = trendMetricKeysForType(canonicalType);
    const primary = specs.find((spec) => spec.factKey === factKey);
    expect(primary).toBeTruthy();

    const metricsData = {
      metrics: [{
        fact_key: factKey,
        label: primary.label,
        value: latest,
        series_points: [
          { date: '2026-07-08', value: latest - 5 },
          { date: '2026-07-09', value: latest },
        ],
      }],
    };

    const built = buildTrendSeriesFromMetrics(metricsData, [primary]);
    expect(built[0].chartData).toHaveLength(2);
    expect(built[0].chartData[1].value).toBe(latest);
    expect(hasTrendMetricDataInBundle(metricsData, [primary])).toBe(true);
  });

  test.each([
    ['compute/vm', 'avg_cpu_pct'],
    ['compute/disk', 'disk_read_iops'],
    ['containers/aks', 'cluster_cpu_pct'],
  ])('mergeTrendSeriesPoints falls back to bundle for %s when API sparse', (canonicalType, factKey) => {
    const bundlePts = [
      { date: '2026-07-08', value: 10 },
      { date: '2026-07-09', value: 20 },
    ];
    const specs = trendMetricKeysForType(canonicalType);
    const primary = specs.find((spec) => spec.factKey === factKey);
    const merged = mergeTrendSeriesPoints([], bundlePts);
    const chart = buildMetricTrendChart(merged, {
      label: primary.label,
      unit: primary.unit,
      factKey,
    });
    expect(chart).toHaveLength(2);
    expect(chart[1].value).toBe(20);
  });
});

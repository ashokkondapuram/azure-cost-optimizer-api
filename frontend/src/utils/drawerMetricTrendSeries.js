import { formatIsoDate } from './format';
import { formatUtilizationTrend } from './evidenceUtils';
import { formatChartMetricValue } from './formatMetricUnits';
import { formatFactValue } from './resourceMetricsUtils';

/** Build line-chart rows from GET /metrics/utilization-series points. */
export function buildMetricTrendChart(points = [], { label = 'Value', unit = '', factKey = '' } = {}) {
  return (points || [])
    .filter((row) => row?.date && row.value != null)
    .map((row) => ({
      date: String(row.date).slice(0, 10),
      dateLabel: formatIsoDate(String(row.date).slice(0, 10)),
      value: Number(row.value),
      label,
      unit,
      factKey,
      formattedValue: formatChartMetricValue(row.value, { factKey, unit }),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function trendSummaryForMetric(trendPayload, label, factKey = '') {
  if (!trendPayload) return null;
  const formatted = formatUtilizationTrend(trendPayload);
  if (!formatted) return null;
  const detail = trendPayload.current_value != null
    ? `Current ${formatFactValue(factKey, trendPayload.current_value)}`
    : null;
  return { label, value: formatted, detail };
}

/** Read dated series points embedded in a drawer metrics bundle row. */
export function extractSeriesPointsFromBundle(metricsData, factKey) {
  if (!metricsData || !factKey) return [];
  const key = String(factKey).toLowerCase();
  const rows = [
    ...(metricsData.metrics || []),
    ...(metricsData.derived || []),
    ...(metricsData.metrics_detail || []),
  ];
  const row = rows.find((entry) => String(entry?.fact_key || '').toLowerCase() === key);
  return Array.isArray(row?.series_points) ? row.series_points : [];
}

/** True when the bundle has a current scalar for a trend metric fact key. */
export function hasTrendMetricValue(metricsData, factKey) {
  if (!metricsData || !factKey) return false;
  const key = String(factKey).toLowerCase();
  const rows = [
    ...(metricsData.metrics || []),
    ...(metricsData.derived || []),
    ...(metricsData.metrics_detail || []),
  ];
  const row = rows.find((entry) => String(entry?.fact_key || '').toLowerCase() === key);
  if (row) {
    const stats = row.stats || {};
    const primary = String(row.primary_stat || '').toLowerCase();
    const raw = row.value
      ?? (primary && stats[primary] != null ? stats[primary] : null)
      ?? stats.average
      ?? stats.maximum
      ?? stats.total
      ?? stats.minimum
      ?? null;
    if (Number.isFinite(Number(raw))) return true;
  }
  const facts = metricsData.facts || {};
  return Number.isFinite(Number(facts[factKey] ?? facts[key]));
}

/** True when any configured trend metric has bundle series or scalar data. */
export function hasTrendMetricDataInBundle(metricsData, metricKeys = []) {
  return (metricKeys || []).some((spec) => {
    if (spec?.static) return false;
    const points = extractSeriesPointsFromBundle(metricsData, spec.factKey);
    return points.length > 0 || hasTrendMetricValue(metricsData, spec.factKey);
  });
}

/** Prefer API/history series; fall back to bundle-embedded Monitor series. */
export function mergeTrendSeriesPoints(primaryPoints = [], fallbackPoints = []) {
  if ((primaryPoints || []).length >= 2) return primaryPoints;
  if ((fallbackPoints || []).length >= 2) return fallbackPoints;
  return (primaryPoints || []).length ? primaryPoints : (fallbackPoints || []);
}

/** Build chart-ready series for each configured trend metric from a metrics bundle. */
export function buildTrendSeriesFromMetrics(metricsData, metricKeys = []) {
  return (metricKeys || []).map((spec) => ({
    spec,
    points: extractSeriesPointsFromBundle(metricsData, spec.factKey),
    chartData: buildMetricTrendChart(
      extractSeriesPointsFromBundle(metricsData, spec.factKey),
      { label: spec.label, unit: spec.unit, factKey: spec.factKey },
    ),
  }));
}

/** Summary card from the latest point in a trend series. */
export function trendSummaryFromSeries(points = [], label, factKey = '', periodLabel = '') {
  if (!points?.length) return null;
  const latest = points[points.length - 1];
  if (latest?.value == null) return null;
  return {
    label,
    value: formatFactValue(factKey, latest.value),
    detail: periodLabel ? `Latest · ${periodLabel}` : 'Latest period value',
  };
}

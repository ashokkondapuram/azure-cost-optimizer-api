/** Format Azure Monitor fact values for resource detail UI. */

const FACT_LABELS = {
  avg_cpu_pct: 'Average CPU utilization',
  avg_mem_pct: 'Average memory utilization',
  avg_memory_pct: 'Average memory utilization',
  used_capacity_bytes: 'Storage capacity used',
  transaction_count: 'Transaction volume',
};

const UNIT_FORMATTERS = {
  percent: (num) => `${num.toFixed(1)}%`,
  usd: (num) => `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
  gb: (num) => `${num.toFixed(2)} GB`,
  seconds: (num) => `${num.toFixed(2)} s`,
  count: (num) => num.toLocaleString(undefined, { maximumFractionDigits: 0 }),
  number: (num) => (Number.isInteger(num) ? num.toLocaleString() : num.toFixed(2)),
};

function humanizeKey(key) {
  return String(key || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function labelForFactKey(factKey, fallbackLabel) {
  if (fallbackLabel) return fallbackLabel;
  return FACT_LABELS[factKey] || humanizeKey(factKey);
}

export function formatFactValue(factKey, value, unit) {
  if (value == null || value === '') return '—';
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);

  if (unit && UNIT_FORMATTERS[unit]) {
    return UNIT_FORMATTERS[unit](num);
  }

  if (unit === 'bytes' || unit === 'bytes_per_sec') {
    if (num >= 1_073_741_824) return `${(num / 1_073_741_824).toFixed(2)} GB`;
    if (num >= 1_048_576) return `${(num / 1_048_576).toFixed(1)} MB`;
    if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`;
    return `${num.toFixed(0)} B`;
  }

  if (factKey.endsWith('_pct') || factKey.endsWith('_percent') || factKey.includes('cpu')) {
    return `${num.toFixed(1)}%`;
  }
  if (factKey.endsWith('_bytes') || factKey.includes('memory')) {
    if (num >= 1_073_741_824) return `${(num / 1_073_741_824).toFixed(2)} GB`;
    if (num >= 1_048_576) return `${(num / 1_048_576).toFixed(1)} MB`;
    if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`;
    return `${num.toFixed(0)} B`;
  }
  if (Number.isInteger(num)) return num.toLocaleString();
  if (Math.abs(num) >= 1000) return num.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return num.toFixed(2);
}

export function formatMetricStatValue(factKey, value, unit) {
  return formatFactValue(factKey, value, unit);
}

const STAT_LABELS = {
  average: 'Avg',
  minimum: 'Min',
  maximum: 'Max',
  total: 'Total',
  count: 'Count',
};

export const DEFAULT_STAT_COLUMNS = [
  { key: 'average', label: 'Avg' },
  { key: 'minimum', label: 'Min' },
  { key: 'maximum', label: 'Max' },
];

export const COUNT_STAT_COLUMNS = [
  { key: 'total', label: 'Total' },
  { key: 'average', label: 'Avg' },
  { key: 'maximum', label: 'Max' },
  { key: 'minimum', label: 'Min' },
];

function columnsFromDisplayStats(displayStats) {
  return displayStats
    .filter((key) => STAT_LABELS[key])
    .map((key) => ({ key, label: STAT_LABELS[key] }));
}

export function statColumnsForMetric(row) {
  const unit = row?.unit;
  const displayStats = row?.display_stats;
  if (Array.isArray(displayStats) && displayStats.length) {
    const columns = columnsFromDisplayStats(displayStats);
    if (columns.length) return columns;
  }
  return unit === 'count' ? COUNT_STAT_COLUMNS : DEFAULT_STAT_COLUMNS;
}

export function metricsSummaryRows(metricsSummary = []) {
  return metricsSummary
    .map((item) => ({
      key: item.fact_key,
      label: labelForFactKey(item.fact_key, item.label),
      metricName: item.metric_name,
      value: item.value,
      stats: item.stats,
      unit: item.unit,
      formatted: formatFactValue(item.fact_key, item.value, item.unit),
      hasValue: item.value != null && item.value !== '',
    }));
}

export function unifiedMetricRows(metrics = [], derived = []) {
  const primary = (metrics || []).map((row) => ({
    ...row,
    label: labelForFactKey(row.fact_key, row.label),
    formatted: formatFactValue(row.fact_key, row.value ?? row.stats?.[row.primary_stat], row.unit),
  }));
  const extra = (derived || []).map((row) => ({
    ...row,
    label: labelForFactKey(row.fact_key, row.label),
    formatted: formatFactValue(row.fact_key, row.value, row.unit),
    isDerived: true,
  }));
  return [...primary, ...extra];
}

export function dataQualityMessage(dataQuality, unavailableReason) {
  if (unavailableReason) return unavailableReason;
  if (dataQuality === 'cost_export_only') {
    return 'Usage is estimated from cost data. Azure Monitor metrics are not available for this resource type.';
  }
  if (dataQuality === 'unavailable') {
    return 'Metrics not available for this resource type.';
  }
  return null;
}

export function optimizationMetricStatusLabel(status) {
  const map = {
    underutilized: 'Underutilized',
    low: 'Low',
    healthy: 'Healthy',
    high: 'High',
    medium: 'Medium',
    critical: 'Critical',
    unavailable: 'Unavailable',
  };
  return map[status] || status || '—';
}

/** Map live Azure Monitor payload rows into finding-evidence performance metric shape. */
export function liveMetricsToEvidencePerformance(metricsPayload) {
  if (!metricsPayload?.ok) return [];
  const rows = [...(metricsPayload.metrics || []), ...(metricsPayload.derived || [])];
  return rows
    .map((row) => {
      const value = row.stats?.average ?? row.value;
      if (value == null || value === '') return null;
      return {
        id: row.fact_key,
        label: row.label || labelForFactKey(row.fact_key),
        value,
        formatted: formatFactValue(row.fact_key, value, row.unit),
        status: row.status,
      };
    })
    .filter(Boolean);
}

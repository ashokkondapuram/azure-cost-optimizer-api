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
  mb: (num) => `${num.toLocaleString(undefined, { maximumFractionDigits: 2 })} MB`,
  milliseconds: (num) => `${num.toLocaleString(undefined, { maximumFractionDigits: 1 })} ms`,
  seconds: (num) => {
    if (num >= 3600) {
      return `${(num / 3600).toLocaleString(undefined, { maximumFractionDigits: 2 })} hr`;
    }
    if (num >= 60) {
      return `${(num / 60).toLocaleString(undefined, { maximumFractionDigits: 1 })} min`;
    }
    return `${num.toLocaleString(undefined, { maximumFractionDigits: 2 })} s`;
  },
  count: (num) => num.toLocaleString(undefined, { maximumFractionDigits: 0 }),
  number: (num) => (Number.isInteger(num) ? num.toLocaleString() : num.toFixed(2)),
};

function formatBytesValue(num) {
  if (num >= 1_073_741_824) return `${(num / 1_073_741_824).toFixed(2)} GB`;
  if (num >= 1_048_576) return `${(num / 1_048_576).toFixed(1)} MB`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`;
  return `${num.toFixed(0)} B`;
}

function formatBytesPerSecondValue(num) {
  if (num >= 1_048_576) return `${(num / 1_048_576).toFixed(2)} MB/s`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KB/s`;
  return `${num.toFixed(0)} B/s`;
}

function isPercentFactKey(factKey) {
  const key = String(factKey || '').toLowerCase();
  if (key.endsWith('_sec') || key.endsWith('_ms') || key.endsWith('_lag_sec')) return false;
  if (key.endsWith('_pct') || key.endsWith('_percent') || key.endsWith('_mem_pct')) return true;
  if (key.includes('availability')) return true;
  return key.includes('cpu');
}

function inferUnitFromFactKey(factKey) {
  const key = String(factKey || '').toLowerCase();
  if (key === 'ingestion_bytes') return 'mb';
  if (key === 'byte_count' || key === 'byte_count_peak') return 'bytes';
  if (key === 'provisioned_throughput') return 'number';
  if (key.endsWith('_ms')) return 'milliseconds';
  if (key.includes('ops_per_sec') || key.endsWith('_qps')) return 'count';
  if (key.endsWith('_sec') || key.endsWith('_lag_sec')) return 'seconds';
  if (isPercentFactKey(factKey)) return 'percent';
  if (key.endsWith('_bps') || (key.endsWith('_rate') && key.includes('bytes'))) return 'bytes_per_sec';
  if (key.endsWith('_iops') || key.includes('operations/sec')) return 'count';
  if (key.includes('throughput') && key.includes('bytes')) return 'bytes_per_sec';
  if (
    key.endsWith('_bytes')
    || key.includes('_bytes_')
    || key.endsWith('_bytes_in')
    || key.endsWith('_bytes_out')
    || key.includes('bytes_dropped')
  ) {
    return 'bytes';
  }
  if (key.endsWith('_gb') || key === 'ingestion_gb') return 'gb';
  if (
    key.endsWith('_count')
    || key.endsWith('_ru')
    || key.endsWith('_hits')
    || key.endsWith('_messages')
    || key.includes('requests')
    || key.includes('runs_')
    || key.endsWith('_pull')
    || key.endsWith('_push')
  ) {
    return 'count';
  }
  return '';
}

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

  const resolvedUnit = unit || inferUnitFromFactKey(factKey);

  if (resolvedUnit && UNIT_FORMATTERS[resolvedUnit]) {
    return UNIT_FORMATTERS[resolvedUnit](num);
  }

  if (resolvedUnit === 'bytes' || resolvedUnit === 'bytes_per_sec') {
    return resolvedUnit === 'bytes_per_sec'
      ? formatBytesPerSecondValue(num)
      : formatBytesValue(num);
  }

  const key = String(factKey || '').toLowerCase();
  if (key.endsWith('_sec') || key.endsWith('_lag_sec')) {
    return UNIT_FORMATTERS.seconds(num);
  }
  if (key.endsWith('_ms')) {
    return UNIT_FORMATTERS.milliseconds(num);
  }

  if (isPercentFactKey(factKey)) {
    return `${num.toFixed(1)}%`;
  }
  if (
    key.endsWith('_bytes')
    || key.includes('_bytes_')
    || key.endsWith('_bytes_in')
    || key.endsWith('_bytes_out')
    || key.includes('bytes_dropped')
    || key.includes('memory')
  ) {
    return formatBytesValue(num);
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

const STAT_COLUMN_ORDER = ['total', 'average', 'minimum', 'maximum', 'count'];

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

/** Normalize API rows so value-only metrics still render in the stats table. */
export function normalizeMetricRow(row) {
  if (!row) return row;
  const stats = { ...(row.stats || {}) };
  const primary = String(row.primary_stat || row.primary_aggregation || 'average').toLowerCase();
  if (row.value != null && row.value !== '') {
    if (stats[primary] == null) stats[primary] = row.value;
    if (primary !== 'average' && stats.average == null && primary === 'total') {
      stats.average = row.value;
    }
  }
  return { ...row, stats };
}

/** Union stat columns across heterogeneous metrics (count vs percent vs bytes). */
export function statColumnsForRows(rows = []) {
  const normalized = (rows || []).map(normalizeMetricRow).filter(Boolean);
  if (!normalized.length) return DEFAULT_STAT_COLUMNS;

  const keySet = new Set();
  normalized.forEach((row) => {
    statColumnsForMetric(row).forEach((col) => keySet.add(col.key));
    Object.entries(row.stats || {}).forEach(([key, value]) => {
      if (value != null && value !== '' && STAT_LABELS[key]) keySet.add(key);
    });
  });

  if (!keySet.size) return DEFAULT_STAT_COLUMNS;

  const ordered = STAT_COLUMN_ORDER
    .filter((key) => keySet.has(key))
    .map((key) => ({ key, label: STAT_LABELS[key] }));

  if (ordered.length) return ordered;

  return DEFAULT_STAT_COLUMNS;
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

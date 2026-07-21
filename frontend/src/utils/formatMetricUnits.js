/** Human-readable metric and property units — bytes → GB/MB, throughput → MB/s, memory → GB/MB. */

const BYTES_IN_KB = 1024;
const BYTES_IN_MB = BYTES_IN_KB ** 2;
const BYTES_IN_GB = BYTES_IN_KB ** 3;
const BYTES_IN_TB = BYTES_IN_KB ** 4;

function finiteNumber(value) {
  if (value == null || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function formatScaled(value, unit, decimals) {
  const formatted = value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${formatted} ${unit}`;
}

/** Auto-scale byte counts to KB, MB, GB, or TB. */
export function formatBytes(value) {
  const num = finiteNumber(value);
  if (num == null) return '—';
  if (num >= BYTES_IN_TB) return formatScaled(num / BYTES_IN_TB, 'TB', num / BYTES_IN_TB >= 10 ? 1 : 2);
  if (num >= BYTES_IN_GB) return formatScaled(num / BYTES_IN_GB, 'GB', num / BYTES_IN_GB >= 10 ? 2 : 2);
  if (num >= BYTES_IN_MB) return formatScaled(num / BYTES_IN_MB, 'MB', 1);
  if (num >= BYTES_IN_KB) return formatScaled(num / BYTES_IN_KB, 'KB', 1);
  return formatScaled(num / BYTES_IN_KB, 'KB', 2);
}

/** Format throughput — prefer MB/s over B/s. Input is bytes per second. */
export function formatThroughput(value) {
  const num = finiteNumber(value);
  if (num == null) return '—';
  if (num >= BYTES_IN_GB) return formatScaled(num / BYTES_IN_GB, 'GB/s', 2);
  if (num >= BYTES_IN_MB) return formatScaled(num / BYTES_IN_MB, 'MB/s', 2);
  const decimals = num >= BYTES_IN_KB ? 3 : 4;
  return formatScaled(num / BYTES_IN_MB, 'MB/s', decimals);
}

/** Format memory byte counts as MB or GB. */
export function formatMemory(value) {
  const num = finiteNumber(value);
  if (num == null) return '—';
  if (num >= BYTES_IN_GB) {
    return formatScaled(num / BYTES_IN_GB, 'GB', num / BYTES_IN_GB >= 10 ? 1 : 2);
  }
  return formatScaled(num / BYTES_IN_MB, 'MB', num / BYTES_IN_MB >= 100 ? 0 : 1);
}

/** Format IOPS — plain count with thousand separators. */
export function formatIops(value) {
  const num = finiteNumber(value);
  if (num == null) return '—';
  return num.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

/** Format CPU utilization or core count. */
export function formatCpu(value, { asPercent = true } = {}) {
  const num = finiteNumber(value);
  if (num == null) return '—';
  if (asPercent) return `${num.toFixed(1)}%`;
  const label = num === 1 ? 'core' : 'cores';
  return `${num.toLocaleString('en-US', { maximumFractionDigits: 1 })} ${label}`;
}

function leafKey(key = '') {
  return String(key).split('.').pop() || String(key);
}

/** Property/fact key already stores GB (e.g. diskSizeGB). */
export function isPreScaledGbKey(key = '') {
  const leaf = leafKey(key).toLowerCase();
  return leaf.endsWith('gb')
    || leaf.endsWith('_gb')
    || leaf === 'size_gb'
    || leaf === 'storage_gb';
}

/** Property/fact key already stores MB. */
export function isPreScaledMbKey(key = '') {
  const leaf = leafKey(key).toLowerCase();
  return leaf.endsWith('mb')
    || leaf.endsWith('_mb')
    || leaf.includes('memoryinmb');
}

export function isBytesFactKey(key = '') {
  const normalized = String(key || '').toLowerCase();
  if (normalized === 'ingestion_bytes') return false;
  if (normalized === 'network_out_bytes' || normalized === 'network_in_bytes') return false;
  return normalized.endsWith('_bytes')
    || normalized.includes('_bytes_')
    || normalized.endsWith('_bytes_in')
    || normalized.endsWith('_bytes_out')
    || normalized.includes('bytes_dropped')
    || normalized === 'byte_count'
    || normalized === 'byte_count_peak';
}

export function isThroughputFactKey(key = '') {
  const normalized = String(key || '').toLowerCase();
  return normalized.endsWith('_bps')
    || normalized === 'network_out_bytes'
    || normalized === 'network_in_bytes'
    || (normalized.endsWith('_rate') && normalized.includes('bytes'))
    || (normalized.includes('throughput') && normalized.includes('bytes'));
}

export function isMemoryFactKey(key = '') {
  const normalized = String(key || '').toLowerCase();
  if (isPreScaledGbKey(key) || isPreScaledMbKey(key)) return false;
  return normalized.includes('memory') && (normalized.includes('bytes') || normalized.includes('_byte'));
}

export function isIopsFactKey(key = '') {
  const normalized = String(key || '').toLowerCase();
  return normalized.endsWith('_iops') || normalized.includes('operations/sec');
}

export function isCountFactKey(key = '') {
  const normalized = String(key || '').toLowerCase();
  if (normalized === 'ingestion_bytes') return false;
  if (normalized === 'byte_count' || normalized === 'byte_count_peak') return false;
  if (normalized.endsWith('_pct') || normalized.endsWith('_percent')) return false;
  return normalized.endsWith('_count')
    || normalized.endsWith('_ru')
    || normalized.endsWith('_hits')
    || normalized.endsWith('_messages')
    || normalized.includes('requests')
    || normalized.includes('runs_')
    || normalized.endsWith('_pull')
    || normalized.endsWith('_push')
    || normalized.includes('ops_per_sec')
    || normalized.endsWith('_qps');
}

export function isPercentFactKey(key = '') {
  const normalized = String(key || '').toLowerCase();
  if (normalized.endsWith('_sec') || normalized.endsWith('_ms') || normalized.endsWith('_lag_sec')) {
    return false;
  }
  if (normalized.endsWith('_pct') || normalized.endsWith('_percent') || normalized.endsWith('_mem_pct')) {
    return true;
  }
  if (normalized.includes('availability')) return true;
  return normalized.includes('cpu') && !normalized.includes('cpu_time');
}

/** Format a property or inventory scalar using key-based unit detection. */
export function formatPropertyMetricValue(key, value) {
  if (value == null || value === '') return null;
  const num = finiteNumber(value);
  if (num == null) return null;

  if (isPreScaledGbKey(key)) {
    return formatScaled(num, 'GB', Number.isInteger(num) ? 0 : 1);
  }
  if (isPreScaledMbKey(key)) {
    return formatScaled(num, 'MB', Number.isInteger(num) ? 0 : 1);
  }
  if (isPercentFactKey(key)) return formatCpu(num, { asPercent: true });
  if (isThroughputFactKey(key)) return formatThroughput(num);
  if (isMemoryFactKey(key)) return formatMemory(num);
  if (isIopsFactKey(key)) return `${formatIops(num)} IOPS`;
  if (isBytesFactKey(key)) return formatBytes(num);

  return null;
}

/** Resolve chart Y-axis suffix from fact key (empty when values are fully formatted). */
export function chartAxisSuffix(factKey = '', unit = '') {
  const normalizedUnit = String(unit || '').trim();
  if (normalizedUnit === '%') return '%';
  if (normalizedUnit && !['B', 'B/s', 'bytes', 'bytes_per_sec'].includes(normalizedUnit)) {
    return normalizedUnit.startsWith(' ') ? normalizedUnit : ` ${normalizedUnit}`;
  }

  const key = String(factKey || '').toLowerCase();
  if (isPercentFactKey(key) || normalizedUnit === 'percent') return '%';
  if (isThroughputFactKey(key)) return '';
  if (isBytesFactKey(key)) return '';
  if (isIopsFactKey(key)) return '';
  return normalizedUnit ? ` ${normalizedUnit}` : '';
}

/** Format chart tooltip / axis tick for a metric value. */
export function formatChartMetricValue(value, { factKey = '', unit = '' } = {}) {
  const num = finiteNumber(value);
  if (num == null) return String(value ?? '—');

  const key = String(factKey || '');
  const normalizedUnit = String(unit || '').trim().toLowerCase();

  if (normalizedUnit === 'count' || isCountFactKey(key)) {
    return formatIops(num);
  }
  if (normalizedUnit === 'percent' || normalizedUnit === '%' || isPercentFactKey(key)) {
    return formatCpu(num, { asPercent: true });
  }
  if (normalizedUnit === 'bytes_per_sec' || normalizedUnit === 'b/s' || isThroughputFactKey(key)) {
    return formatThroughput(num);
  }
  if (normalizedUnit === 'bytes' || normalizedUnit === 'b' || isBytesFactKey(key)) {
    return formatBytes(num);
  }
  if (isMemoryFactKey(key)) return formatMemory(num);
  if (isIopsFactKey(key)) return formatIops(num);
  if (isPreScaledGbKey(key)) return formatScaled(num, 'GB', 1);
  if (Number.isInteger(num)) return num.toLocaleString('en-US');
  if (Math.abs(num) >= 1000) {
    return num.toLocaleString('en-US', { maximumFractionDigits: 1 });
  }
  return num.toFixed(2);
}

/** Compact axis tick — omits unit suffix (Recharts appends unit prop separately when needed). */
export function formatChartAxisTick(value, options = {}) {
  const formatted = formatChartMetricValue(value, options);
  return formatted
    .replace(/\s+(TB|GB|MB|KB|GB\/s|MB\/s|KB\/s|IOPS|cores?)$/i, '')
    .replace(/%$/, '');
}

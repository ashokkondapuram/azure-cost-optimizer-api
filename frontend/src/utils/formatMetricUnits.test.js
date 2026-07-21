import {
  chartAxisSuffix,
  formatBytes,
  formatChartAxisTick,
  formatChartMetricValue,
  formatCpu,
  formatIops,
  formatMemory,
  formatPropertyMetricValue,
  formatThroughput,
  isBytesFactKey,
  isCountFactKey,
  isMemoryFactKey,
  isPercentFactKey,
  isPreScaledGbKey,
  isPreScaledMbKey,
  isThroughputFactKey,
} from './formatMetricUnits';

describe('formatMetricUnits', () => {
  describe('formatBytes', () => {
    test('auto-scales storage capacity', () => {
      expect(formatBytes(512)).toBe('0.50 KB');
      expect(formatBytes(2048)).toBe('2.0 KB');
      expect(formatBytes(5_368_709_120)).toBe('5.00 GB');
      expect(formatBytes(1_500_000_000)).toBe('1.40 GB');
      expect(formatBytes(1_099_511_627_776)).toBe('1.00 TB');
    });

    test('handles invalid input', () => {
      expect(formatBytes(null)).toBe('—');
      expect(formatBytes('n/a')).toBe('—');
    });
  });

  describe('formatThroughput', () => {
    test('prefers MB/s over B/s', () => {
      expect(formatThroughput(512)).toBe('0.0005 MB/s');
      expect(formatThroughput(2048)).toBe('0.002 MB/s');
      expect(formatThroughput(1_048_576)).toBe('1.00 MB/s');
      expect(formatThroughput(1_073_741_824)).toBe('1.00 GB/s');
    });
  });

  describe('formatMemory', () => {
    test('shows MB or GB for memory bytes', () => {
      expect(formatMemory(62_262_717_653)).toBe('58.0 GB');
      expect(formatMemory(512_000_000)).toBe('488 MB');
    });
  });

  describe('formatCpu and formatIops', () => {
    test('formats CPU percent and core counts', () => {
      expect(formatCpu(32.84)).toBe('32.8%');
      expect(formatCpu(4, { asPercent: false })).toBe('4 cores');
      expect(formatCpu(1, { asPercent: false })).toBe('1 core');
    });

    test('formats IOPS with thousand separators', () => {
      expect(formatIops(5000)).toBe('5,000');
    });
  });

  describe('formatPropertyMetricValue', () => {
    test('detects pre-scaled GB and MB property keys', () => {
      expect(formatPropertyMetricValue('diskSizeGB', 128)).toBe('128 GB');
      expect(formatPropertyMetricValue('size_gb', 512)).toBe('512 GB');
      expect(formatPropertyMetricValue('memoryInMB', 8192)).toBe('8,192 MB');
    });

    test('detects byte and throughput fact keys', () => {
      expect(formatPropertyMetricValue('used_capacity_bytes', 1_073_741_824)).toBe('1.00 GB');
      expect(formatPropertyMetricValue('network_out_bytes', 2_097_152)).toBe('2.00 MB/s');
      expect(formatPropertyMetricValue('avg_available_memory_bytes', 8_589_934_592)).toBe('8.00 GB');
    });

    test('returns null for non-metric properties', () => {
      expect(formatPropertyMetricValue('vmSize', 128)).toBeNull();
      expect(formatPropertyMetricValue('name', 'vm-01')).toBeNull();
    });
  });

  describe('key detection helpers', () => {
    test('identifies byte, memory, and percent keys', () => {
      expect(isBytesFactKey('egress_bytes')).toBe(true);
      expect(isBytesFactKey('ingestion_bytes')).toBe(false);
      expect(isMemoryFactKey('avg_available_memory_bytes')).toBe(true);
      expect(isPercentFactKey('avg_cpu_pct')).toBe(true);
      expect(isPercentFactKey('cpu_time_sec')).toBe(false);
      expect(isPreScaledGbKey('diskSizeGB')).toBe(true);
      expect(isPreScaledMbKey('memoryInMB')).toBe(true);
      expect(isThroughputFactKey('disk_read_bps')).toBe(true);
    });
  });

  describe('chart formatters', () => {
    test('formats chart values and axis ticks', () => {
      expect(formatChartMetricValue(45.2, { factKey: 'avg_cpu_pct', unit: '%' })).toBe('45.2%');
      expect(formatChartMetricValue(1_048_576, { factKey: 'network_out_bytes', unit: 'bytes_per_sec' })).toBe('1.00 MB/s');
      expect(formatChartMetricValue(5_368_709_120, { factKey: 'egress_bytes', unit: 'bytes' })).toBe('5.00 GB');
      expect(formatChartMetricValue(3220.23, { factKey: 'pod_count', unit: 'count' })).toBe('3,220');
      expect(formatChartAxisTick(45.2, { factKey: 'avg_cpu_pct', unit: '%' })).toBe('45.2');
      expect(chartAxisSuffix('avg_cpu_pct', '%')).toBe('%');
      expect(chartAxisSuffix('egress_bytes', 'bytes')).toBe('');
    });

    test('identifies count fact keys', () => {
      expect(isCountFactKey('pod_count')).toBe(true);
      expect(isCountFactKey('request_count')).toBe(true);
      expect(isCountFactKey('byte_count')).toBe(false);
    });
  });
});

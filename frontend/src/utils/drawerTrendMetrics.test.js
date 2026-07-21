import {
  trendMetricKeysForResource,
  trendMetricKeysForType,
  resolveDrawerCanonicalType,
  hasTrendSummaryMetrics,
  noTrendSummaryMetricsMessage,
  visibleTrendSummaryCards,
  TREND_SUMMARY_METRICS_BY_TYPE,
} from './drawerTrendMetrics';

const DISK = {
  id: '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/disks/data-disk',
  name: 'data-disk',
  type: 'Microsoft.Compute/disks',
};

const VM = {
  id: '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm-web-01',
  name: 'vm-web-01',
  type: 'Microsoft.Compute/virtualMachines',
};

const AGW = {
  id: '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Network/applicationGateways/agw1',
  type: 'Microsoft.Network/applicationGateways',
};

const SQL_SERVER = {
  id: '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Sql/servers/sql1',
  type: 'Microsoft.Sql/servers',
};

describe('drawerTrendMetrics', () => {
  test('trendMetricKeysForType returns disk I/O metrics without CPU', () => {
    const keys = trendMetricKeysForType('compute/disk');
    const factKeys = keys.map((k) => k.factKey);
    expect(factKeys).toEqual(expect.arrayContaining([
      'disk_read_iops',
      'disk_write_iops',
      'disk_read_bps',
      'disk_write_bps',
    ]));
    expect(keys.some((k) => k.label.includes('CPU'))).toBe(false);
  });

  test('trendMetricKeysForType returns CPU and network for VMs without disk queue depth', () => {
    const keys = trendMetricKeysForType('compute/vm');
    const factKeys = keys.map((k) => k.factKey);
    expect(factKeys).toEqual([
      'avg_cpu_pct',
      'avg_memory_pct',
      'max_cpu_pct',
      'network_out_bytes',
    ]);
    expect(factKeys).not.toContain('disk_queue_depth');
    expect(keys[0].analysisTrendKey).toBe('cpu_trend');
  });

  test('trendMetricKeysForResource resolves disk from ARM id without api path', () => {
    const keys = trendMetricKeysForResource(DISK, '');
    expect(keys.map((k) => k.factKey)).toEqual(expect.arrayContaining([
      'disk_read_iops',
      'disk_write_iops',
    ]));
  });

  test('resolveDrawerCanonicalType uses api path when provided', () => {
    expect(resolveDrawerCanonicalType(DISK, '/resources/disks')).toBe('compute/disk');
    expect(resolveDrawerCanonicalType(VM, '/resources/vms')).toBe('compute/vm');
  });

  test('storage account metrics exclude CPU and include transactions and availability', () => {
    const keys = trendMetricKeysForType('storage/account');
    const factKeys = keys.map((k) => k.factKey);
    expect(factKeys).toEqual(expect.arrayContaining([
      'transaction_count',
      'ingress_bytes',
      'egress_bytes',
      'availability_pct',
    ]));
    expect(factKeys.some((k) => k.includes('cpu'))).toBe(false);
  });

  test('application gateway uses backend health and throughput metrics', () => {
    const keys = trendMetricKeysForType('network/appgateway');
    const factKeys = keys.map((k) => k.factKey);
    expect(factKeys).toEqual(expect.arrayContaining([
      'healthy_host_count',
      'throughput_bytes',
      'failed_request_count',
    ]));
    expect(keys.every((k) => !k.static)).toBe(true);
    expect(factKeys.some((k) => k.includes('cpu'))).toBe(false);
  });

  test('load balancer metrics exclude generic CPU/memory', () => {
    const keys = trendMetricKeysForType('network/loadbalancer');
    const factKeys = keys.map((k) => k.factKey);
    expect(factKeys).toEqual(expect.arrayContaining([
      'backend_availability_pct',
      'byte_count',
    ]));
    expect(factKeys.some((k) => k.includes('cpu'))).toBe(false);
  });

  test('AKS cluster uses cluster CPU and memory metrics', () => {
    const keys = trendMetricKeysForType('containers/aks');
    expect(keys.map((k) => k.factKey)).toEqual([
      'cluster_cpu_pct',
      'cluster_mem_pct',
      'pod_count',
    ]);
    expect(keys.find((k) => k.factKey === 'pod_count')?.unit).toBe('count');
  });

  test('Redis uses monitor fact keys not Azure metric names', () => {
    const keys = trendMetricKeysForType('database/redis');
    expect(keys.map((k) => k.factKey)).toEqual([
      'memory_pct',
      'server_load_pct',
      'ops_per_sec',
    ]);
  });

  test('Cosmos DB trend metrics align with monitor profile fact keys', () => {
    const keys = trendMetricKeysForType('database/cosmosdb');
    const factKeys = keys.map((k) => k.factKey);
    expect(factKeys).toEqual(expect.arrayContaining([
      'normalized_ru_pct',
      'normalized_ru_peak_pct',
      'total_ru',
      'provisioned_throughput',
    ]));
  });

  test('SQL server has no trend summary metrics', () => {
    expect(trendMetricKeysForType('database/sql')).toEqual([]);
    expect(hasTrendSummaryMetrics('database/sql')).toBe(false);
    expect(trendMetricKeysForResource(SQL_SERVER, '')).toEqual([]);
  });

  test('unknown resource types do not fall back to generic CPU/memory', () => {
    const keys = trendMetricKeysForType('analytics/databricks');
    expect(keys).toEqual([]);
    expect(hasTrendSummaryMetrics('analytics/databricks')).toBe(false);
  });

  test('noTrendSummaryMetricsMessage returns user-facing empty state copy', () => {
    expect(noTrendSummaryMetricsMessage()).toBe('No utilization metrics for this resource type');
  });

  test('TREND_SUMMARY_METRICS_BY_TYPE exports per-type mapping', () => {
    expect(TREND_SUMMARY_METRICS_BY_TYPE['compute/vm'].length).toBeGreaterThan(0);
    expect(TREND_SUMMARY_METRICS_BY_TYPE['network/appgateway'].some(
      (m) => m.factKey === 'failed_request_count',
    )).toBe(true);
  });

  test('cosmos DB trend metrics align with monitor profile fact keys', () => {
    const keys = trendMetricKeysForType('database/cosmosdb');
    expect(keys.map((k) => k.factKey)).toEqual([
      'normalized_ru_pct',
      'normalized_ru_peak_pct',
      'total_ru',
      'provisioned_throughput',
      'data_usage_bytes',
    ]);
  });

  test('trendMetricKeysForResource resolves application gateway from ARM id', () => {
    const keys = trendMetricKeysForResource(AGW, '');
    expect(keys.some((k) => k.factKey === 'healthy_host_count')).toBe(true);
  });

  test('visibleTrendSummaryCards hides cards when utilization charts exist for same metric', () => {
    const metricKeys = trendMetricKeysForType('database/cosmosdb');
    const summaryCards = metricKeys.map((spec) => ({
      label: spec.label,
      value: '0.1%',
      detail: 'Latest · Last 7 days',
    }));

    const visible = visibleTrendSummaryCards(
      summaryCards,
      metricKeys,
      ['normalized_ru_pct', 'normalized_ru_peak_pct', 'total_ru'],
    );

    expect(visible).toHaveLength(2);
    expect(visible.map((card) => card.label)).toEqual([
      'Provisioned throughput',
      'Data usage',
    ]);
  });

  test('visibleTrendSummaryCards keeps all cards when no charts are available', () => {
    const metricKeys = trendMetricKeysForType('compute/vm');
    const summaryCards = metricKeys.map((spec) => ({
      label: spec.label,
      value: '12%',
      detail: 'Current period · Last 7 days',
    }));

    expect(visibleTrendSummaryCards(summaryCards, metricKeys, [])).toEqual(summaryCards);
  });

  test('visibleTrendSummaryCards keeps static property cards even when charts exist', () => {
    const metricKeys = [
      { factKey: 'backend_pool_count', label: 'Backend pools', static: true },
      { factKey: 'healthy_host_count', label: 'Healthy backend hosts' },
    ];
    const summaryCards = [
      { label: 'Backend pools', value: '3' },
      { label: 'Healthy backend hosts', value: '2' },
    ];

    const visible = visibleTrendSummaryCards(
      summaryCards,
      metricKeys,
      ['healthy_host_count'],
    );

    expect(visible).toEqual([
      { label: 'Backend pools', value: '3' },
    ]);
  });
});

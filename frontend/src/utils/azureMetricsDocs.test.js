import { azureMetricsDocUrl } from './azureMetricsDocs';

describe('azureMetricsDocUrl', () => {
  test('builds supported-metrics Learn URL from doc_ref slug', () => {
    expect(azureMetricsDocUrl('microsoft-compute-virtualmachines-metrics')).toBe(
      'https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-compute-virtualmachines-metrics',
    );
  });

  test('appends -metrics when slug is omitted', () => {
    expect(azureMetricsDocUrl('microsoft-cache-redis')).toBe(
      'https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-cache-redis-metrics',
    );
  });

  test('returns null for empty input', () => {
    expect(azureMetricsDocUrl('')).toBeNull();
    expect(azureMetricsDocUrl(null)).toBeNull();
  });
});

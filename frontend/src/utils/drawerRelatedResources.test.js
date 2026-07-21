import {
  resolveRelatedResources,
  metricValuesFromPayload,
} from './drawerRelatedResources';
import { trendMetricKeysForType, trendMetricKeysForResource } from './drawerCapabilities';

const DISK_ID = '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/disks/data-disk';
const VM_ID = '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm-web-01';
const QUEUE_ID = '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.ServiceBus/namespaces/ns/queues/q1';

describe('drawerRelatedResources', () => {
  test('trendMetricKeysForType returns disk metrics for disks', () => {
    const keys = trendMetricKeysForType('compute/disk');
    expect(keys.some((k) => k.factKey.includes('iops'))).toBe(true);
    expect(keys.some((k) => k.label.includes('CPU'))).toBe(false);
  });

  test('trendMetricKeysForType returns CPU metrics for VMs', () => {
    const keys = trendMetricKeysForType('compute/vm');
    expect(keys[0].factKey).toBe('avg_cpu_pct');
  });

  test('trendMetricKeysForResource resolves disk from ARM id', () => {
    const keys = trendMetricKeysForResource({
      id: DISK_ID,
      type: 'Microsoft.Compute/disks',
    }, '');
    expect(keys.some((k) => k.factKey === 'disk_read_iops')).toBe(true);
  });

  test('trendMetricKeysForType returns application gateway monitor metrics', () => {
    const keys = trendMetricKeysForType('network/appgateway');
    expect(keys.map((k) => k.factKey)).toEqual(expect.arrayContaining([
      'healthy_host_count',
      'throughput_bytes',
      'failed_request_count',
    ]));
    expect(keys.some((k) => k.factKey.includes('cpu'))).toBe(false);
  });

  test('resolveRelatedResources links disk to attached VM', () => {
    const disk = {
      id: DISK_ID,
      type: 'Microsoft.Compute/disks',
      properties: { managedBy: VM_ID },
    };
    const related = resolveRelatedResources(disk);
    expect(related.some((r) => r.id.toLowerCase() === VM_ID.toLowerCase())).toBe(true);
    expect(related[0].relation).toMatch(/VM/i);
  });

  test('resolveRelatedResources links queue to namespace', () => {
    const queue = {
      id: QUEUE_ID,
      type: 'Microsoft.ServiceBus/namespaces/queues',
    };
    const related = resolveRelatedResources(queue);
    expect(related.some((r) => r.relation === 'Namespace')).toBe(true);
  });

  test('metricValuesFromPayload extracts metric values', () => {
    const values = metricValuesFromPayload({
      metrics: [{ fact_key: 'avg_cpu_pct', value: 42, stats: { average: 42 } }],
    }, [{ factKey: 'avg_cpu_pct', label: 'CPU', unit: '%' }]);
    expect(values.avg_cpu_pct.value).toBe(42);
  });
});

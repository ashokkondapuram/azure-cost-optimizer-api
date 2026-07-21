import { normalizeDiskFromApi, apiRowsToConceptDisks } from '../diskApiModel';

describe('diskApiModel', () => {
  test('normalizeDiskFromApi maps enriched API shape', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-01',
      name: 'disk-01',
      resourceGroup: 'rg',
      location: 'canadacentral',
      sku: 'Premium_LRS',
      properties: {
        diskSizeGB: 128,
        diskState: 'Unattached',
        tier: 'P15',
      },
      metrics: { disk_iops_utilization_pct: 8 },
      cost: {
        billed_mtd: 12.5,
        retail_monthly: 48,
        retail_currency: 'CAD',
      },
      finding: {
        rule_id: 'DISK_UNUSED_EXTENDED',
        severity: 'high',
        savings: 48,
        workflow: 'proposed',
        source: 'engine',
      },
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.name).toBe('disk-01');
    expect(disk.properties.sku).toBe('Premium_LRS');
    expect(disk.properties.diskState).toBe('Unattached');
    expect(disk.metrics.disk_iops_utilization_pct).toBe(8);
    expect(disk.cost.billed_mtd).toBe(12.5);
    expect(disk.finding.rule_id).toBe('DISK_UNUSED_EXTENDED');
  });

  test('normalizeDiskFromApi uses flat billing when nested billed_mtd is zero', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-02',
      name: 'disk-02',
      monthlyCostBilling: 58.06,
      billingCurrency: 'CAD',
      cost: {
        billed_mtd: 0,
        cost_pending: true,
      },
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.cost.billed_mtd).toBe(58.06);
  });

  test('normalizeDiskFromApi merges assessment_properties EAV into properties', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-03',
      name: 'disk-03',
      sku: 'Premium_LRS',
      properties: {},
      assessment_properties: {
        diskSizeGB: '256',
        diskState: 'Attached',
        diskIOPSReadWrite: '5000',
        diskMBpsReadWrite: '200',
        managedBy: '/subscriptions/sub/.../virtualMachines/vm-01',
        provisioningState: 'Succeeded',
      },
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.properties.diskSizeGB).toBe(256);
    expect(disk.properties.diskState).toBe('Attached');
    expect(disk.properties.diskIOPSReadWrite).toBe(5000);
    expect(disk.properties.managedBy).toContain('virtualMachines');
  });

  test('normalizeDiskFromApi merges property_rows when assessment_properties absent', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-04',
      name: 'disk-04',
      property_rows: [
        { property_key: 'diskSizeGB', property_value: '128' },
        { property_key: 'diskState', property_value: 'Unattached' },
      ],
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.properties.diskSizeGB).toBe(128);
    expect(disk.properties.diskState).toBe('Unattached');
    expect(disk.properties.managedBy).toBe('—');
  });

  test('normalizeDiskFromApi merges metricsFacts into metrics', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-05',
      name: 'disk-05',
      metricsFacts: {
        disk_iops_utilization_pct: 12,
        disk_throughput_utilization_pct: 6,
      },
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.metrics.disk_iops_utilization_pct).toBe(12);
    expect(disk.metrics.disk_throughput_utilization_pct).toBe(6);
  });

  test('normalizeDiskFromApi prefers nested cost.retail_monthly', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-06',
      retail_monthly: 99,
      cost: {
        billed_mtd: 10,
        retail_monthly: 42,
        retail_currency: 'CAD',
        retail_source: 'resource_sku_pricing',
      },
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.cost.retail_monthly).toBe(42);
    expect(disk.cost.retail_source).toBe('resource_sku_pricing');
  });

  test('normalizeDiskFromApi unwraps nested assessment_properties.flat envelope', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-07',
      name: 'disk-07',
      assessment_properties: {
        flat: { diskSizeGB: '64', diskState: 'Attached' },
        rows: [],
      },
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.properties.diskSizeGB).toBe(64);
    expect(disk.properties.diskState).toBe('Attached');
  });

  test('normalizeDiskFromApi never throws on malformed properties', () => {
    const row = {
      id: '/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-08',
      name: 'disk-08',
      properties: 'invalid',
      metrics: 'invalid',
    };

    const disk = normalizeDiskFromApi(row);
    expect(disk.name).toBe('disk-08');
    expect(disk.properties).toEqual({});
    expect(disk.metrics).toEqual({});
  });

  test('apiRowsToConceptDisks skips null entries and keeps valid rows', () => {
    const rows = apiRowsToConceptDisks([
      null,
      { id: '/subscriptions/sub/.../disks/a', name: 'a' },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe('a');
  });
});

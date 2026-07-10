import {
  diskLastOwnershipUpdate,
  diskSku,
  diskStateLabel,
  diskAttachmentSummary,
  getDiskHostAttachment,
  getDiskPropertyTiles,
  getDiskUsageTiles,
  diskProvisionedIopsLabel,
  diskProvisionedMbpsLabel,
  diskSizeGbLabel,
  isDiskResource,
} from '../utils/diskUtils';

describe('compute-disk diskUtils', () => {
  test('detects disk resources', () => {
    expect(isDiskResource({ type: 'Microsoft.Compute/disks' })).toBe(true);
    expect(isDiskResource({}, '/resources/disks')).toBe(true);
    expect(isDiskResource({ type: 'Microsoft.Compute/snapshots' })).toBe(false);
  });

  test('reads last ownership update from synced properties only', () => {
    expect(diskLastOwnershipUpdate({
      properties: { lastOwnershipUpdateTime: '2026-04-23T12:11:15Z' },
    })).toBe('2026-04-23T12:11:15Z');
    expect(diskLastOwnershipUpdate({ lastOwnershipUpdateTime: '2026-04-23T12:11:15Z' }))
      .toBeNull();
  });

  test('formats disk sku and state labels', () => {
    const disk = {
      sku: { name: 'Premium_LRS' },
      properties: { diskState: 'Attached' },
    };
    expect(diskSku(disk)).toBe('Premium_LRS');
    expect(diskStateLabel(disk)).toBe('Attached');
  });

  test('builds disk property tiles for drawer summary', () => {
    const tiles = getDiskPropertyTiles({
      sku: 'StandardSSD_LRS',
      location: 'eastus',
      resourceGroup: 'rg-prod',
      state: 'Unattached',
      properties: {
        diskSizeGB: 128,
        diskState: 'Unattached',
        diskIOPSReadWrite: 500,
        diskMBpsReadWrite: 100,
        timeCreated: '2024-01-15T10:00:00Z',
        lastOwnershipUpdateTime: '2026-04-23T12:11:15Z',
        lastManagedBy: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1',
        provisioningState: 'Succeeded',
      },
    });

    expect(tiles.map((t) => t.label)).toEqual([
      'SKU',
      'Disk state',
      'Provisioned size',
      'Provisioned IOPS',
      'Provisioned throughput',
      'Attached to',
      'Last compute type',
      'Last attached to',
      'Provisioning state',
      'Created',
      'Last ownership update',
    ]);
    expect(tiles.find((t) => t.key === 'size')?.value).toBe('128 GB');
    expect(tiles.find((t) => t.key === 'disk-state')?.tone).toBe('warn');
  });

  test('reads PascalCase ARM disk properties', () => {
    const tiles = getDiskPropertyTiles({
      properties: {
        DiskSizeGB: 256,
        DiskIOPSReadWrite: 1100,
        DiskMBpsReadWrite: 125,
        DiskState: 'Attached',
        ManagedBy: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1',
      },
    });
    expect(tiles.find((t) => t.key === 'size')?.value).toBe('256 GB');
    expect(tiles.find((t) => t.key === 'iops')?.value).toBe('1,100');
    expect(tiles.find((t) => t.key === 'mbps')?.value).toBe('125 MB/s');
    expect(tiles.find((t) => t.key === 'attached-type')?.value).toBe('Virtual machine');
    expect(tiles.find((t) => t.key === 'attached-host')?.value).toBe('vm-1');
  });

  test('maps VMSS instance attachments', () => {
    const armId = '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/app-vmss/virtualMachines/2';
    const host = getDiskHostAttachment({
      properties: {
        diskState: 'Attached',
        managedBy: armId,
      },
    });
    expect(host.status).toBe('attached');
    expect(host.attachment?.kind).toBe('vmss_instance');
    expect(diskAttachmentSummary({ properties: { managedBy: armId } })).toBe('app-vmss / instance 2');

    const tiles = getDiskPropertyTiles({ properties: { diskState: 'Attached', managedBy: armId } });
    expect(tiles.find((t) => t.key === 'attached-vmss')?.value).toBe('app-vmss');
  });

  test('builds usage tiles from monitor metrics bundle', () => {
    const resource = {
      properties: { diskIOPSReadWrite: 1100, diskMBpsReadWrite: 125 },
    };
    const usage = getDiskUsageTiles({
      ok: true,
      timespan: 'P7D',
      metrics: [
        {
          fact_key: 'disk_read_iops',
          label: 'Disk read IOPS',
          stats: { average: 12.5, maximum: 40 },
        },
        {
          fact_key: 'disk_paid_burst_iops',
          label: 'On-demand burst operations',
          stats: { average: 3, maximum: 8 },
        },
      ],
      derived: [
        {
          fact_key: 'disk_iops_utilization_pct',
          label: 'Disk IOPS utilization',
          value: 42.1,
          unit: 'percent',
        },
      ],
    }, { resource });
    expect(usage.map((t) => t.label)).toEqual([
      'Disk read IOPS',
      'On-demand burst operations',
      'Disk IOPS utilization',
    ]);
    expect(usage[0].value).toBe('13 avg · 40 max · 1,100 provisioned');
    expect(usage[1].value).toBe('3 avg · 8 max');
    expect(usage[2].value).toBe('42.1%');
  });

  test('reads provisioned capacity from technical facts', () => {
    expect(diskProvisionedIopsLabel({
      properties: {},
      _technical_facts: { provisioned_iops: 5000, provisioned_mbps: 200, size_gb: 512 },
    })).toBe('5,000');
    expect(diskProvisionedMbpsLabel({
      properties: {},
      _technical_facts: { provisioned_mbps: 200 },
    })).toBe('200 MB/s');
    expect(diskSizeGbLabel({
      properties: {},
      _technical_facts: { size_gb: 512 },
    })).toBe('512 GB');
  });

  test('derives provisioned IOPS and throughput from SKU tier when ARM omits them', () => {
    const resource = {
      sku: { name: 'Premium_LRS' },
      properties: { diskSizeGB: 512, diskState: 'Attached' },
    };
    expect(diskProvisionedIopsLabel(resource)).toBe('3,500');
    expect(diskProvisionedMbpsLabel(resource)).toBe('170 MB/s');
  });

  test('uses properties.tier from Disks GET when present', () => {
    const resource = {
      sku: { name: 'Premium_LRS' },
      properties: { diskSizeGB: 512, tier: 'P50', diskState: 'Attached' },
    };
    expect(diskProvisionedIopsLabel(resource)).toBe('7,500');
    expect(diskProvisionedMbpsLabel(resource)).toBe('250 MB/s');
  });

  test('resolves host from managedByExtended', () => {
    const attachment = getDiskHostAttachment({
      properties: {
        diskState: 'Attached',
        managedByExtended: [
          '/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/shared-vm',
        ],
      },
    });
    expect(attachment.status).toBe('attached');
    expect(attachment.attachment?.name).toBe('shared-vm');
  });
});

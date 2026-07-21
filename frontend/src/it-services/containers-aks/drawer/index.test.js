import { enrichDrawerResource } from '../drawer';

describe('containers-aks drawer', () => {
  const cluster = {
    name: 'prod-aks',
    type: 'Microsoft.ContainerService/managedClusters',
    properties: {
      agentPoolProfiles: [
        { name: 'system', count: 2, vmSize: 'Standard_D2s_v3', mode: 'System' },
      ],
    },
  };

  test('enriches drawer resource with normalized pools and utilization', () => {
    const enriched = enrichDrawerResource(cluster, {
      apiPath: '/resources/aks',
      metricsData: {
        facts: { cluster_cpu_pct: 25 },
        pool_metrics: [{ name: 'system', cpu_pct: 25, mem_pct: 55, source: 'cluster' }],
      },
    });

    expect(enriched._pools).toHaveLength(1);
    expect(enriched._pools[0]).toMatchObject({
      name: 'system',
      cpuPct: 25,
      memPct: 55,
      utilizationSource: 'cluster',
    });
    expect(enriched._nodeCount).toBe(2);
  });

  test('preserves VMSS identity through drawer enrichment', () => {
    const enriched = enrichDrawerResource({
      ...cluster,
      properties: {
        ...cluster.properties,
        agentPoolProfiles: [{
          name: 'system',
          count: 2,
          vmSize: 'Standard_D2s_v3',
          mode: 'System',
          virtualMachineScaleSet: {
            id: '/subscriptions/sub-a/resourceGroups/MC_rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-12345678-vmss',
          },
        }],
      },
    }, {
      apiPath: '/resources/aks',
      metricsData: { facts: {}, pool_metrics: [] },
    });

    expect(enriched._pools[0]).toMatchObject({
      _vmssName: 'aks-system-12345678-vmss',
      vmssSource: 'synced',
    });
  });

  test('attaches VMSS instances from pool_metrics to drawer pools', () => {
    const enriched = enrichDrawerResource(cluster, {
      apiPath: '/resources/aks',
      metricsData: {
        facts: {},
        pool_metrics: [{
          name: 'system',
          cpu_pct: 30,
          mem_pct: 50,
          source: 'node',
          vmss_instances: [{
            name: 'aks-system-node-0',
            instance_id: '0',
            power_state: 'running',
            cpu_pct: 30,
            mem_pct: 50,
            source: 'k8s_agent',
          }],
        }],
      },
    });

    expect(enriched._pools[0].instances).toHaveLength(1);
    expect(enriched._pools[0].instances[0]).toMatchObject({
      name: 'aks-system-node-0',
      instanceId: '0',
      cpuPct: 30,
      memPct: 50,
      metricsSource: 'k8s_agent',
    });
  });
});

import {
  normalizeAksPools,
  normalizeAksCluster,
} from './aksNormalize';
import {
  aggregatePoolUtilization,
  attachPoolInstances,
  matchNodeToPool,
} from './aksPoolUtilization';
import {
  matchPoolVmss,
  resolvePoolVmssRef,
} from './aksVmssMatch';

describe('aksNormalize', () => {
  test('normalizes agent pool profiles with autoscale range', () => {
    const cluster = {
      name: 'prod-aks',
      properties: {
        agentPoolProfiles: [
          {
            name: 'system',
            count: 2,
            vmSize: 'Standard_D2s_v3',
            mode: 'System',
            enableAutoScaling: true,
            minCount: 1,
            maxCount: 5,
          },
          {
            name: 'user',
            properties: {
              count: 3,
              vmSize: 'Standard_D4s_v3',
              mode: 'User',
            },
          },
        ],
      },
    };

    const normalized = normalizeAksCluster(cluster);
    expect(normalized._pools).toHaveLength(2);
    expect(normalized._pools[0]).toMatchObject({
      name: 'system',
      count: 2,
      enableAutoScaling: true,
      autoscaleRange: '1 – 5',
    });
    expect(normalized._pools[1].vmSize).toBe('Standard_D4s_v3');
    expect(normalized._nodeCount).toBe(5);
  });

  test('returns empty pools when agentPoolProfiles missing', () => {
    expect(normalizeAksPools({ properties: {} })).toEqual([]);
  });

  test('labels NAP pools with Auto provisioning mode', () => {
    const cluster = {
      properties: {
        nodeProvisioningProfile: { mode: 'Auto' },
        agentPoolProfiles: [
          { name: 'system', count: 2, vmSize: 'Standard_D2s_v3', mode: 'System' },
          {
            name: 'gpu',
            count: 3,
            vmSize: 'Standard_NC6s_v3',
            mode: 'Auto provisioning',
            _napPool: true,
            virtualMachineScaleSet: {
              id: '/subscriptions/sub-a/resourceGroups/MC_rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-gpu-abcdef01-vmss',
              name: 'aks-gpu-abcdef01-vmss',
            },
          },
        ],
      },
    };

    const normalized = normalizeAksCluster(cluster);
    expect(normalized._pools).toHaveLength(2);
    expect(normalized._pools[1]).toMatchObject({
      name: 'gpu',
      mode: 'Auto provisioning',
      _napPool: true,
      _vmssName: 'aks-gpu-abcdef01-vmss',
    });
  });

  test('derives node auto provisioning from nodeProvisioningProfile.mode', () => {
    const enabled = normalizeAksCluster({
      properties: {
        nodeProvisioningProfile: { mode: 'Auto', defaultNodePools: 'Auto' },
      },
    });
    expect(enabled._nodeAutoProvisioning).toBe('Enabled');
    expect(enabled._nodeAutoProvisioningEnabled).toBe(true);

    const disabled = normalizeAksCluster({
      properties: {
        nodeProvisioningProfile: { mode: 'Manual' },
      },
    });
    expect(disabled._nodeAutoProvisioning).toBe('Disabled');
    expect(disabled._nodeAutoProvisioningEnabled).toBe(false);

    const missing = normalizeAksCluster({ properties: {} });
    expect(missing._nodeAutoProvisioning).toBe('Disabled');
    expect(missing._nodeAutoProvisioningEnabled).toBe(false);
  });

  test('attaches VMSS identity from synced pool properties', () => {
    const cluster = {
      id: '/subscriptions/sub-a/resourceGroups/rg-prod/providers/Microsoft.ContainerService/managedClusters/prod-aks',
      properties: {
        nodeResourceGroup: 'MC_rg-prod_prod-aks_eastus',
        agentPoolProfiles: [
          {
            name: 'system',
            count: 2,
            virtualMachineScaleSet: {
              id: '/subscriptions/sub-a/resourceGroups/MC_rg-prod_prod-aks_eastus/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-12345678-vmss',
              name: 'aks-system-12345678-vmss',
            },
          },
        ],
      },
    };

    const normalized = normalizeAksCluster(cluster);
    expect(normalized._pools[0]).toMatchObject({
      name: 'system',
      _vmssName: 'aks-system-12345678-vmss',
      vmssSource: 'synced',
    });
    expect(normalized._pools[0]._vmssId).toContain('virtualMachineScaleSets/aks-system-12345678-vmss');
  });

  test('resolves VMSS from _vmssByPool when pool profile omits direct ref', () => {
    const cluster = {
      properties: {
        nodeResourceGroup: 'MC_rg-prod_prod-aks_eastus',
        agentPoolProfiles: [{ name: 'user', count: 3, vmSize: 'Standard_D4s_v3' }],
        _vmssByPool: {
          user: {
            id: '/subscriptions/sub-a/resourceGroups/MC_rg-prod_prod-aks_eastus/providers/Microsoft.Compute/virtualMachineScaleSets/aks-user-87654321-vmss',
            name: 'aks-user-87654321-vmss',
          },
        },
      },
    };

    const normalized = normalizeAksCluster(cluster);
    expect(normalized._pools[0]).toMatchObject({
      _vmssName: 'aks-user-87654321-vmss',
      vmssSource: 'synced',
    });
  });

  test('does not derive VMSS without synced pool or map data', () => {
    const cluster = {
      properties: {
        nodeResourceGroup: 'MC_rg-prod_prod-aks_eastus',
        agentPoolProfiles: [{ name: 'user', count: 3, vmSize: 'Standard_D4s_v3' }],
      },
    };

    const normalized = normalizeAksCluster(cluster);
    expect(normalized._pools[0].vmssId).toBeNull();
    expect(normalized._pools[0].vmssSource).toBeNull();
  });
});

describe('aksVmssMatch', () => {
  test('matches pool to VMSS by aks-{pool}- prefix', () => {
    const vmss = matchPoolVmss('system', [
      { name: 'aks-system-12345678-vmss', id: '/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-12345678-vmss' },
    ]);
    expect(vmss?.name).toBe('aks-system-12345678-vmss');
  });

  test('resolvePoolVmssRef prefers synced virtualMachineScaleSet id', () => {
    const ref = resolvePoolVmssRef({
      name: 'system',
      virtualMachineScaleSet: {
        id: '/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-abc',
      },
    });
    expect(ref).toMatchObject({
      vmssName: 'aks-system-abc',
      vmssSource: 'synced',
    });
  });

  test('resolvePoolVmssRef falls back to _vmssByPool map', () => {
    const ref = resolvePoolVmssRef(
      { name: 'system' },
      {
        system: {
          id: '/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-abc',
          name: 'aks-system-abc',
        },
      },
    );
    expect(ref).toMatchObject({
      vmssName: 'aks-system-abc',
      vmssSource: 'synced',
    });
  });
});

describe('aksPoolUtilization', () => {
  const pools = normalizeAksPools({
    properties: {
      agentPoolProfiles: [
        { name: 'system', count: 2, vmSize: 'Standard_D2s_v3' },
        { name: 'user', count: 3, vmSize: 'Standard_D4s_v3' },
      ],
    },
  });

  test('matches node keys to pool names', () => {
    const prefixes = [
      { name: 'system', prefix: 'prod-aks-system', poolNameLower: 'system', clusterName: 'prod-aks' },
    ];
    expect(matchNodeToPool('prod-aks-system-abc123', 'prod-aks', prefixes)).toBe('system');
    expect(matchNodeToPool('prod-aks/aks-user-xyz', 'prod-aks', [
      { name: 'user', prefix: 'prod-aks-user', poolNameLower: 'user', clusterName: 'prod-aks' },
    ])).toBe('user');
  });

  test('aggregates per-pool CPU and memory from node instances', () => {
    const enriched = aggregatePoolUtilization('prod-aks', pools, [
      {
        name: 'prod-aks-system-node1',
        metrics_detail: [
          { fact_key: 'node_cpu_pct', stats: { average: 20 } },
          { fact_key: 'node_mem_pct', stats: { average: 40 } },
        ],
      },
      {
        name: 'prod-aks-system-node2',
        metrics_detail: [
          { fact_key: 'node_cpu_pct', stats: { average: 40 } },
          { fact_key: 'node_mem_pct', stats: { average: 60 } },
        ],
      },
      {
        pool_name: 'user',
        metrics_detail: [
          { fact_key: 'node_cpu_pct', stats: { average: 10 } },
          { fact_key: 'node_mem_pct', stats: { average: 30 } },
        ],
      },
    ]);

    expect(enriched[0]).toMatchObject({
      name: 'system',
      cpuPct: 30,
      memPct: 50,
      utilizationSource: 'node',
      nodesWithMetrics: 2,
    });
    expect(enriched[1]).toMatchObject({
      name: 'user',
      cpuPct: 10,
      memPct: 30,
      utilizationSource: 'node',
    });
  });

  test('falls back to cluster-level metrics when node metrics are absent', () => {
    const enriched = aggregatePoolUtilization(
      'prod-aks',
      pools,
      [],
      { cluster_cpu_pct: 18.5, cluster_mem_pct: 62.0 },
    );
    expect(enriched[0]).toMatchObject({
      cpuPct: 18.5,
      memPct: 62.0,
      utilizationSource: 'cluster',
    });
  });

  test('uses VMSS metrics from backend pool_metrics when K8s metrics are absent', () => {
    const enriched = aggregatePoolUtilization(
      'prod-aks',
      pools,
      [],
      {},
      [{
        name: 'system',
        cpu_pct: 42.5,
        mem_pct: 61.0,
        source: 'vmss',
        vmss_id: '/subscriptions/sub-a/resourceGroups/MC_rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss',
        vmss_instance_count: 3,
      }],
    );
    expect(enriched[0]).toMatchObject({
      name: 'system',
      cpuPct: 42.5,
      memPct: 61.0,
      utilizationSource: 'vmss',
      count: 3,
    });
  });

  test('attachPoolInstances maps backend vmss_instances onto pools', () => {
    const poolsWithUtil = aggregatePoolUtilization('prod-aks', pools, [], {}, []);
    const withInstances = attachPoolInstances(poolsWithUtil, [{
      name: 'system',
      vmss_instances: [{
        id: '/subscriptions/sub-a/resourceGroups/MC_rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss/virtualMachines/0',
        name: 'aks-system-123-vmss000000',
        instance_id: '0',
        power_state: 'running',
        cpu_pct: 35.5,
        mem_pct: 48.0,
        source: 'k8s_agent',
      }],
    }]);
    expect(withInstances[0].instances).toHaveLength(1);
    expect(withInstances[0].instances[0]).toMatchObject({
      name: 'aks-system-123-vmss000000',
      instanceId: '0',
      powerState: 'running',
      cpuPct: 35.5,
      memPct: 48.0,
      metricsSource: 'k8s_agent',
    });
  });

  test('attachPoolInstances falls back to synced vmssInstances without metrics', () => {
    const poolsWithSynced = [{
      name: 'system',
      count: 2,
      vmssInstances: [{
        id: '/subscriptions/sub-a/resourceGroups/MC_rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss/virtualMachines/0',
        name: 'aks-system-123-vmss000000',
        instance_id: '0',
        power_state: 'running',
      }],
    }];
    const withInstances = attachPoolInstances(poolsWithSynced, []);
    expect(withInstances[0].instances[0]).toMatchObject({
      name: 'aks-system-123-vmss000000',
      instanceId: '0',
      powerState: 'running',
      cpuPct: null,
      memPct: null,
    });
  });
});

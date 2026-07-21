import {
  applicationGatewayCounts,
  drawerPropertyMetricSpecs,
  drawerStaticMetricCards,
  enrichDrawerEssentials,
  hasDrawerPropertyMetrics,
  isApplicationGateway,
  shouldHideGenericMetrics,
} from './drawerResourceTypeMetrics';

const AGW = {
  id: '/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Network/applicationGateways/prod-agw',
  type: 'Microsoft.Network/applicationGateways',
  canonical_type: 'network/appgateway',
  properties: {
    backendAddressPools: [{ name: 'pool-a' }, { name: 'pool-b' }],
    probes: [{ name: 'probe-https' }],
  },
};

describe('drawerResourceTypeMetrics', () => {
  test('isApplicationGateway matches canonical and ARM types', () => {
    expect(isApplicationGateway('network/appgateway')).toBe(true);
    expect(isApplicationGateway('', 'microsoft.network/applicationgateways')).toBe(true);
    expect(isApplicationGateway('compute/vm')).toBe(false);
  });

  test('shouldHideGenericMetrics hides CPU/memory for application gateways', () => {
    expect(shouldHideGenericMetrics('network/appgateway')).toBe(true);
    expect(shouldHideGenericMetrics('compute/vm')).toBe(false);
  });

  test('drawerPropertyMetricSpecs returns pool and probe counts only', () => {
    const specs = drawerPropertyMetricSpecs('network/appgateway', 'Microsoft.Network/applicationGateways');
    expect(specs?.length).toBeGreaterThan(0);
    expect(specs?.some((s) => s.factKey === 'backend_pool_count')).toBe(true);
    expect(specs?.some((s) => s.factKey === 'health_probe_count')).toBe(true);
    expect(specs?.every((s) => s.static)).toBe(true);
  });

  test('applicationGatewayCounts reads synced property arrays', () => {
    expect(applicationGatewayCounts(AGW)).toEqual({
      backend_pool_count: 2,
      health_probe_count: 1,
    });
  });

  test('applicationGatewayCounts prefers inventory payload values', () => {
    const counts = applicationGatewayCounts(AGW, {
      inventory_properties: [
        { fact_key: 'backend_pool_count', value: 3 },
        { fact_key: 'health_probe_count', value: 4 },
      ],
    });
    expect(counts).toEqual({
      backend_pool_count: 3,
      health_probe_count: 4,
    });
  });

  test('drawerStaticMetricCards builds summary cards from property counts', () => {
    const specs = drawerPropertyMetricSpecs('network/appgateway', 'Microsoft.Network/applicationGateways');
    const cards = drawerStaticMetricCards(AGW, specs, null, {
      canonicalType: 'network/appgateway',
      armType: 'Microsoft.Network/applicationGateways',
    });
    expect(cards.length).toBeGreaterThan(0);
    expect(cards.some((card) => card.label === 'Backend pools' && card.value === '2')).toBe(true);
    expect(cards.some((card) => card.label === 'Health probes' && card.value === '1')).toBe(true);
  });

  test('enrichDrawerEssentials adds AKS node auto provisioning', () => {
    const rows = [];
    enrichDrawerEssentials(rows, {
      type: 'containers/aks',
      properties: {
        nodeProvisioningProfile: { mode: 'Auto' },
        agentPoolProfiles: [{ name: 'system', count: 2 }],
      },
    }, new Set(), '');
    expect(rows.map((r) => r.label)).toEqual(expect.arrayContaining(['Node auto provisioning']));
    expect(rows.find((r) => r.label === 'Node auto provisioning')?.value).toBe('Enabled');
  });

  test('enrichDrawerEssentials adds pool and probe rows', () => {
    const rows = [];
    enrichDrawerEssentials(rows, AGW, new Set());
    expect(rows.map((r) => r.label)).toEqual(['Backend pools', 'Health probes']);
    expect(rows[0].value).toBe('2');
    expect(rows[1].value).toBe('1');
  });

  test('enrichDrawerEssentials adds listeners and rules when present', () => {
    const rows = [];
    const resource = {
      ...AGW,
      properties: {
        ...AGW.properties,
        httpListeners: [{ name: 'l1' }, { name: 'l2' }],
        requestRoutingRules: [{ name: 'r1' }],
      },
    };
    enrichDrawerEssentials(rows, resource, new Set());
    expect(rows.map((r) => r.label)).toEqual([
      'Backend pools',
      'Health probes',
      'Listeners',
      'Rules',
    ]);
  });

  test('enrichDrawerEssentials skips pool summary when requested', () => {
    const rows = [];
    enrichDrawerEssentials(rows, {
      type: 'containers/aks',
      properties: {
        agentPoolProfiles: [{ name: 'system', count: 2 }],
      },
    }, new Set(), '/resources/aks', null, { skipPoolSummary: true });
    expect(rows.map((r) => r.label)).not.toContain('Node pools');
    expect(rows.map((r) => r.label)).toEqual(expect.arrayContaining(['Nodes', 'Node auto provisioning']));
  });
});

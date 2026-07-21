import {
  buildApplicationGatewaySummaryRows,
  httpListenerCount,
  isApplicationGatewayResource,
  isApplicationGatewaySummaryPropertyKey,
  matchesApplicationGateway,
} from './applicationGatewayPropertySummary';

const AGW_RESOURCE = {
  type: 'Microsoft.Network/applicationGateways',
  canonical_type: 'network/appgateway',
  properties: {
    backendAddressPools: [{ name: 'pool-a' }, { name: 'pool-b' }, { name: 'pool-c' }],
    probes: [{ name: 'probe-https' }, { name: 'probe-http' }],
    httpListeners: [{ name: 'l1' }, { name: 'l2' }, { name: 'l3' }, { name: 'l4' }],
    requestRoutingRules: [{ name: 'r1' }, { name: 'r2' }, { name: 'r3' }, { name: 'r4' }, { name: 'r5' }],
    sku: { name: 'Standard_v2', tier: 'Standard_v2', capacity: 2 },
  },
};

describe('applicationGatewayPropertySummary', () => {
  test('matchesApplicationGateway detects ARM and canonical types', () => {
    expect(matchesApplicationGateway(AGW_RESOURCE)).toBe(true);
    expect(matchesApplicationGateway(AGW_RESOURCE, '/resources/appgateways')).toBe(true);
    expect(matchesApplicationGateway({ type: 'Microsoft.Compute/disks' })).toBe(false);
  });

  test('isApplicationGatewaySummaryPropertyKey recognizes synced ARM arrays', () => {
    expect(isApplicationGatewaySummaryPropertyKey('backendAddressPools')).toBe(true);
    expect(isApplicationGatewaySummaryPropertyKey('probes')).toBe(true);
    expect(isApplicationGatewaySummaryPropertyKey('httpListeners')).toBe(true);
    expect(isApplicationGatewaySummaryPropertyKey('requestRoutingRules')).toBe(true);
    expect(isApplicationGatewaySummaryPropertyKey('sku')).toBe(false);
  });

  test('httpListenerCount falls back to routing rule listener refs', () => {
    expect(httpListenerCount({
      httpListeners: [],
      requestRoutingRules: [
        {
          properties: {
            httpListener: {
              id: '/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw/httpListeners/l1',
            },
          },
        },
        {
          properties: {
            httpListener: {
              id: '/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw/httpListeners/l2',
            },
          },
        },
      ],
    })).toBe(2);
  });

  test('buildApplicationGatewaySummaryRows returns count labels only', () => {
    expect(buildApplicationGatewaySummaryRows(AGW_RESOURCE.properties)).toEqual([
      { key: 'agw-backend-pools', label: 'Backend pools', value: '3' },
      { key: 'agw-health-probes', label: 'Health probes', value: '2' },
      { key: 'agw-listeners', label: 'Listeners', value: '4' },
      { key: 'agw-rules', label: 'Rules', value: '5' },
    ]);
  });

  test('isApplicationGatewayResource accepts api path hint', () => {
    expect(isApplicationGatewayResource({}, '/resources/appgateways')).toBe(true);
  });
});

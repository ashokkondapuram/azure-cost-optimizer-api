import { getDrawerOverviewTiles, buildCompleteDrawerEssentials } from './resourceDrawerUtils';

const APPLICATION_GATEWAY = {
  name: 'prod-agw',
  type: 'Microsoft.Network/applicationGateways',
  canonical_type: 'network/appgateway',
  location: 'eastus',
  resourceGroup: 'rg-net',
  sku: 'Standard_v2',
  state: 'Succeeded',
  properties: {
    backendAddressPools: [
      { name: 'pool-a', properties: { backendAddresses: [{ ipAddress: '10.0.0.4' }] } },
      { name: 'pool-b', properties: { backendAddresses: [] } },
      { name: 'pool-c', properties: { backendAddresses: [] } },
    ],
    probes: [
      { name: 'probe-https', properties: { protocol: 'Https', path: '/health' } },
      { name: 'probe-http', properties: { protocol: 'Http', path: '/' } },
    ],
    httpListeners: [
      { name: 'listener-1', properties: { protocol: 'Https', frontendPort: { id: 'port-443' } } },
      { name: 'listener-2', properties: { protocol: 'Http', frontendPort: { id: 'port-80' } } },
      { name: 'listener-3', properties: { protocol: 'Https' } },
      { name: 'listener-4', properties: { protocol: 'Http' } },
    ],
    requestRoutingRules: [
      { name: 'rule-1', properties: { ruleType: 'Basic' } },
      { name: 'rule-2', properties: { ruleType: 'Basic' } },
      { name: 'rule-3', properties: { ruleType: 'PathBasedRouting' } },
      { name: 'rule-4', properties: { ruleType: 'Basic' } },
      { name: 'rule-5', properties: { ruleType: 'Basic' } },
    ],
    sku: { name: 'Standard_v2', tier: 'Standard_v2', capacity: 2 },
    backendHttpSettingsCollection: [{ name: 'setting-1' }],
    frontendIPConfigurations: [{ name: 'appGwPublicFrontendIp' }],
    frontendPorts: [{ name: 'port-443' }, { name: 'port-80' }],
  },
};

describe('getDrawerOverviewTiles', () => {
  test('includes inventory fields without cost tile', () => {
    const tiles = getDrawerOverviewTiles({
      location: 'eastus',
      resourceGroup: 'rg-prod',
      state: 'running',
      sku: 'Standard_D2s_v3',
    });

    expect(tiles.some((t) => /cost/i.test(t.label))).toBe(false);
    expect(tiles.map((t) => t.label)).toEqual(
      expect.arrayContaining(['Status', 'SKU']),
    );
    expect(tiles.map((t) => t.label)).not.toEqual(
      expect.arrayContaining(['Location', 'Resource group']),
    );
  });

  test('includes AKS node auto provisioning in overview', () => {
    const essentials = buildCompleteDrawerEssentials({
      name: 'nap-aks',
      type: 'containers/aks',
      properties: {
        nodeProvisioningProfile: { mode: 'Auto' },
        agentPoolProfiles: [{ name: 'system', count: 2, vmSize: 'Standard_D2s_v3' }],
      },
    }, [], { apiPath: '/resources/aks' });

    const labels = essentials.rows.map((row) => row.label);
    expect(labels).toEqual(expect.arrayContaining(['Node auto provisioning']));
    expect(labels.filter((label) => label === 'Node auto provisioning')).toHaveLength(1);
    const nap = essentials.rows.find((row) => row.label === 'Node auto provisioning');
    expect(nap?.value).toBe('Enabled');
  });

  test('dedupes AKS essentials from inventory properties and enrichment', () => {
    const essentials = buildCompleteDrawerEssentials({
      name: 'aks-dedupe',
      type: 'containers/aks',
      _pools: [{ name: 'system', count: 2, vmSize: 'Standard_D2s_v3' }],
      _nodeCount: 2,
      properties: {
        nodeProvisioningProfile: { mode: 'Auto' },
        kubernetesVersion: '1.29.2',
        agentPoolProfiles: [{ name: 'system', count: 2, vmSize: 'Standard_D2s_v3' }],
      },
    }, [
      { fact_key: 'node_auto_provisioning', label: 'Node auto provisioning', value: 'Enabled' },
      { fact_key: 'pool_count', label: 'Node pool count', value: 1 },
      { fact_key: 'node_count', label: 'Total node count', value: 2 },
    ], { apiPath: '/resources/aks' });

    const labels = essentials.rows.map((row) => row.label);
    expect(labels.filter((label) => label === 'Node auto provisioning')).toHaveLength(1);
    expect(labels.filter((label) => label === 'Node pools')).toHaveLength(0);
    expect(labels.filter((label) => label === 'Nodes')).toHaveLength(1);
    expect(labels.filter((label) => /version/i.test(label))).toHaveLength(1);
  });

  test('includes AKS-specific fields when present', () => {
    const tiles = getDrawerOverviewTiles({
      _version: '1.29.2',
      _nodeCount: 3,
      location: 'westus',
    });

    expect(tiles.map((t) => t.label)).toEqual(
      expect.arrayContaining(['Version', 'Nodes']),
    );
  });

  test('disk overview keeps analysis fields only', () => {
    const essentials = buildCompleteDrawerEssentials({
      name: 'data-disk-01',
      type: 'Microsoft.Compute/disks',
      canonical_type: 'compute/disk',
      sku: 'Premium_LRS',
      state: 'Unattached',
      properties: {
        diskSizeGB: 512,
        diskState: 'Unattached',
        diskIOPSReadWrite: 2300,
        diskMBpsReadWrite: 150,
        managedBy: null,
        encryption: { type: 'EncryptionAtRestWithPlatformKey' },
        shareInfo: [],
      },
    }, [], { apiPath: '/resources/disks' });

    const labels = essentials.rows.map((row) => row.label);
    expect(labels).toEqual(expect.arrayContaining(['Status', 'SKU']));
    expect(labels.some((label) => /disk size/i.test(label))).toBe(true);
    expect(labels.some((label) => /encryption/i.test(label))).toBe(false);
    expect(labels.some((label) => /share info/i.test(label))).toBe(false);
  });

  test('merges analysis-essential ARM properties into overview', () => {
    const essentials = buildCompleteDrawerEssentials({
      name: 'stgacct01',
      type: 'Microsoft.Storage/storageAccounts',
      location: 'eastus',
      resourceGroup: 'rg-storage',
      sku: 'Standard_LRS',
      state: 'Available',
      properties: {
        accessTier: 'Hot',
        kind: 'StorageV2',
        supportsHttpsTrafficOnly: true,
        minimumTlsVersion: 'TLS1_2',
      },
    }, [], { apiPath: '/resources/storage' });

    const labels = essentials.rows.map((row) => row.label);
    expect(labels).toEqual(expect.arrayContaining(['Status', 'SKU']));
    expect(labels.some((label) => /access tier/i.test(label) || label === 'Tier')).toBe(true);
    expect(labels.some((row) => /supports https traffic only/i.test(row))).toBe(false);
    expect(essentials.allPropertySections?.length).toBeGreaterThan(0);
    expect(essentials.allPropertySections.some((section) => (
      section.rows.some((row) => /supports https/i.test(row.label))
    ))).toBe(true);
  });

  test('summarizes application gateway nested properties as counts', () => {
    const essentials = buildCompleteDrawerEssentials(
      APPLICATION_GATEWAY,
      [],
      { apiPath: '/resources/appgateways' },
    );

    const labels = essentials.rows.map((row) => row.label);
    expect(labels).toEqual(expect.arrayContaining([
      'Backend pools',
      'Health probes',
    ]));
    expect(labels).not.toEqual(expect.arrayContaining([
      'Listeners',
      'Rules',
      'Backend Address Pools',
      'Http Listeners',
      'Request Routing Rules',
    ]));

    const backendPools = essentials.rows.find((row) => row.label === 'Backend pools');
    expect(backendPools?.value).toBe('3');

    expect(essentials.propertySections).toHaveLength(0);
    expect(essentials.technicalPropertySections.length).toBeGreaterThan(0);
    expect(essentials.technicalPropertySections.some((section) => (
      section.label.toLowerCase() === 'sku'
    ))).toBe(true);
  });
});

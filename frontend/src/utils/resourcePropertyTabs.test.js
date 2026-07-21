import {
  buildResourcePropertyGroups,
  filterDrawerHeaderPropertyRows,
  flattenPropertyRows,
  humanizePropertyKey,
  isNoisePropertyRow,
} from './resourcePropertyTabs';

describe('resourcePropertyTabs', () => {
  it('humanizes camelCase keys', () => {
    expect(humanizePropertyKey('osProfile')).toBe('Os Profile');
    expect(humanizePropertyKey('timeCreated')).toBe('Time Created');
  });

  it('builds nested ARM property groups for VMs', () => {
    const groups = buildResourcePropertyGroups({
      state: 'running',
      properties: {
        timeCreated: '2026-06-24T15:02:53.851221+00:00',
        osProfile: {
          computerName: 'vm-01',
          adminUsername: 'azureuser',
        },
        instanceView: {
          statuses: [{ code: 'PowerState/running' }],
        },
        storageProfile: {
          osDisk: { name: 'disk1' },
        },
        hardwareProfile: {
          vmSize: 'Standard_D2s_v3',
        },
      },
    }, []);

    expect(groups.some((g) => g.id === 'prop:general')).toBe(true);
    expect(groups.find((g) => g.id === 'prop:general')?.rows.some((r) => r.fact_key === 'timeCreated')).toBe(true);
    expect(groups.some((g) => g.label === 'Os Profile')).toBe(true);
    expect(groups.some((g) => g.label === 'Instance View')).toBe(true);
    expect(groups.some((g) => g.label === 'Storage Profile')).toBe(true);
    expect(groups.some((g) => g.label === 'Hardware Profile')).toBe(true);

    const os = groups.find((g) => g.id === 'prop:osProfile');
    expect(os.rows.some((r) => r.label === 'Computer Name')).toBe(true);
  });

  it('merges unmatched inventory properties into general', () => {
    const groups = buildResourcePropertyGroups(
      { name: 'vm-01', properties: { hardwareProfile: { vmSize: 'Standard_B2s' } } },
      [{ fact_key: 'avg_cpu', label: 'Avg CPU', value: 12 }],
    );
    const general = groups.find((g) => g.id === 'prop:general');
    expect(general?.rows.some((r) => r.fact_key === 'avg_cpu')).toBe(true);
    expect(groups.some((g) => g.id === 'prop:inventory')).toBe(false);
  });

  it('includes overview essential scalars in property groups', () => {
    const groups = buildResourcePropertyGroups({
      name: 'disk-01',
      type: 'Microsoft.Compute/disks',
      location: 'canadacentral',
      resourceGroup: 'rg-apps',
      sku: 'Premium_LRS',
      state: 'Attached',
      properties: {
        diskSizeGB: 128,
        diskState: 'Attached',
        provisioningState: 'Succeeded',
      },
    }, []);

    const general = groups.find((g) => g.id === 'prop:general');
    expect(general?.rows.some((r) => r.fact_key === 'diskSizeGB')).toBe(true);
    expect(general?.rows.find((r) => r.fact_key === 'diskSizeGB')?.formatted).toBe('128 GB');
    expect(general?.rows.some((r) => r.fact_key === 'diskState')).toBe(true);
    expect(general?.rows.some((r) => r.fact_key === 'provisioningState')).toBe(false);
  });

  it('keeps technical ARM scalars not shown in overview essentials', () => {
    const groups = buildResourcePropertyGroups({
      name: 'stgacct01',
      type: 'Microsoft.Storage/storageAccounts',
      location: 'eastus',
      resourceGroup: 'rg-storage',
      properties: {
        supportsHttpsTrafficOnly: true,
      },
    }, []);
    const general = groups.find((g) => g.id === 'prop:general');
    expect(general?.rows.find((r) => r.fact_key === 'supportsHttpsTrafficOnly')?.formatted).toBe('Yes');
  });

  it('flattens nested objects for display rows', () => {
    const rows = flattenPropertyRows({ osDisk: { name: 'd1', diskSizeGB: 128 } }, 'storageProfile');
    expect(rows.some((r) => r.fact_key.includes('osDisk'))).toBe(true);
    expect(rows.some((r) => r.label === 'Value')).toBe(false);
  });

  it('collapses ARM typed parameters into one labeled row', () => {
    const rows = flattenPropertyRows({
      enableNoPublicIp: { type: 'Bool', value: false },
      Environment: { type: 'String', value: 'dev' },
      storageAccountName: { type: 'String', value: 'dbstoragee4y7vxexuatoc' },
    }, 'parameters');

    expect(rows).toHaveLength(3);
    expect(rows.find((r) => r.fact_key === 'parameters.enableNoPublicIp')).toMatchObject({
      label: 'Enable No Public Ip',
      formatted: 'No',
    });
    expect(rows.find((r) => r.fact_key === 'parameters.Environment')).toMatchObject({
      label: 'Environment',
      formatted: 'dev',
    });
    expect(rows.find((r) => r.fact_key === 'parameters.storageAccountName')).toMatchObject({
      label: 'Storage Account Name',
      formatted: 'dbstoragee4y7vxexuatoc',
    });
    expect(rows.some((r) => r.label === 'Type' || r.label === 'Value')).toBe(false);
  });

  it('builds readable Databricks workspace property groups', () => {
    const groups = buildResourcePropertyGroups({
      name: 'adb-dev',
      type: 'Microsoft.Databricks/workspaces',
      location: 'eastus',
      resourceGroup: 'rg-analytics',
      properties: {
        parameters: {
          enableNoPublicIp: { type: 'Bool', value: true },
          Environment: { type: 'String', value: 'dev' },
          Application: { type: 'String', value: 'databricks' },
          storageAccountName: { type: 'String', value: 'dbstoragee4y7vxexuatoc' },
          storageAccountSkuName: { type: 'String', value: 'Standard_GRS' },
        },
        authorizations: {
          principalId: { type: 'String', value: '00000000-0000-0000-0000-000000000001' },
          roleDefinitionId: { type: 'String', value: '00000000-0000-0000-0000-000000000002' },
        },
      },
    }, []);

    const parameters = groups.find((g) => g.id === 'prop:parameters');
    expect(parameters?.rows.some((r) => r.label === 'Type')).toBe(false);
    expect(parameters?.rows.some((r) => r.label === 'Value')).toBe(false);
    expect(parameters?.rows.find((r) => r.fact_key === 'parameters.enableNoPublicIp')?.formatted).toBe('Yes');
    expect(parameters?.rows.find((r) => r.fact_key === 'parameters.Environment')?.formatted).toBe('dev');
    expect(parameters?.rows.find((r) => r.fact_key === 'parameters.storageAccountSkuName')?.formatted).toBe('Standard_GRS');
  });

  it('builds readable storage account nested properties', () => {
    const groups = buildResourcePropertyGroups({
      name: 'stgacct01',
      type: 'Microsoft.Storage/storageAccounts',
      location: 'eastus',
      resourceGroup: 'rg-storage',
      properties: {
        accessTier: 'Hot',
        supportsHttpsTrafficOnly: true,
        encryption: {
          services: {
            blob: { enabled: true, keyType: 'Account' },
            file: { enabled: true, keyType: 'Account' },
          },
          keySource: 'Microsoft.Storage',
        },
      },
    }, []);

    const encryption = groups.find((g) => g.id === 'prop:encryption');
    expect(encryption?.rows.some((r) => r.label === 'Value')).toBe(false);
    expect(encryption?.rows.some((r) => r.label.includes('Blob'))).toBe(true);
    const general = groups.find((g) => g.id === 'prop:general');
    expect(general?.rows.find((r) => r.fact_key === 'supportsHttpsTrafficOnly')?.formatted).toBe('Yes');
  });

  it('flags ARM schema noise rows', () => {
    expect(isNoisePropertyRow({ label: 'Type', value: 'Bool' })).toBe(true);
    expect(isNoisePropertyRow({ label: 'Value', fact_key: 'parameters.enableNoPublicIp.value', value: false })).toBe(true);
    expect(isNoisePropertyRow({ label: 'Enable No Public Ip', fact_key: 'parameters.enableNoPublicIp', value: false })).toBe(false);
  });

  it('formats Cosmos DB account properties for display', () => {
    const groups = buildResourcePropertyGroups({
      name: 'cosmosnosql-account-pncdevv2rg1eu2',
      type: 'Microsoft.DocumentDB/databaseAccounts',
      location: 'eastus2',
      resourceGroup: 'pncdevv2rg1eu2',
      azureServiceName: 'Azure Cosmos DB',
      state: 'Succeeded',
      properties: {
        locations: [{ locationName: 'East US 2', failoverPriority: 0 }],
        capabilities: [],
        enableFreeTier: false,
        enableAutomaticFailover: true,
        enableMultipleWriteLocations: false,
        databaseAccountOfferType: 'Standard',
        consistencyPolicy: {
          defaultConsistencyLevel: 'Session',
          maxStalenessPrefix: 100,
          maxIntervalInSeconds: 5,
        },
      },
    }, []);

    const general = groups.find((g) => g.id === 'prop:general');
    const locations = general?.rows.find((r) => r.fact_key === 'locations');
    expect(locations?.formatted).toBe('East US 2, primary');
    expect(general?.rows.find((r) => r.fact_key === 'capabilities')?.formatted).toBe('None');
    expect(general?.rows.find((r) => r.fact_key === 'enableFreeTier')?.formatted).toBe('No');
    expect(general?.rows.find((r) => r.fact_key === 'enableAutomaticFailover')?.formatted).toBe('Yes');

    const consistency = groups.find((g) => g.id === 'prop:consistencyPolicy');
    expect(consistency?.rows.some((r) => r.label === 'Default Consistency Level')).toBe(true);
  });

  it('deduplicates essentials when filtering with seen keys', () => {
    const seen = new Set(['location', 'sku', 'resourcegroup', 'name', 'type']);
    const rows = filterDrawerHeaderPropertyRows([
      { fact_key: 'name', label: 'Name', value: 'vm-01', formatted: 'vm-01' },
      { fact_key: 'location', label: 'Location', value: 'eastus', formatted: 'eastus' },
      { fact_key: 'sku', label: 'SKU', value: 'Standard_D2s_v3', formatted: 'Standard_D2s_v3' },
      { fact_key: 'type', label: 'ARM type', value: 'Microsoft.Compute/virtualMachines', formatted: 'Virtual Machines' },
      { fact_key: 'supportsHttpsTrafficOnly', label: 'Supports Https Traffic Only', value: true, formatted: 'Yes' },
    ], seen);
    expect(rows).toHaveLength(1);
    expect(rows[0].fact_key).toBe('supportsHttpsTrafficOnly');
  });
});

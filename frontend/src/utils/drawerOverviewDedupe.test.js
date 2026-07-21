import { isOverviewEssentialKey, isOverviewEssentialRow, essentialsRowMatchKey, dedupeEssentialRows } from './drawerOverviewDedupe';

describe('drawerOverviewDedupe', () => {
  it('flags core inventory fields as overview essentials', () => {
    expect(isOverviewEssentialKey('location')).toBe(true);
    expect(isOverviewEssentialKey('resourceGroup')).toBe(true);
    expect(isOverviewEssentialKey('sku')).toBe(true);
    expect(isOverviewEssentialKey('provisioningState')).toBe(true);
  });

  it('flags disk overview fields as essentials', () => {
    expect(isOverviewEssentialKey('diskSizeGB')).toBe(true);
    expect(isOverviewEssentialKey('diskIOPSReadWrite')).toBe(true);
    expect(isOverviewEssentialKey('managedBy')).toBe(true);
  });

  it('keeps technical ARM scalars out of essentials', () => {
    expect(isOverviewEssentialKey('supportsHttpsTrafficOnly')).toBe(false);
    expect(isOverviewEssentialKey('enableAutomaticFailover')).toBe(false);
  });

  it('filters disk created date shown in overview essentials', () => {
    expect(isOverviewEssentialRow({
      fact_key: 'timeCreated',
      label: 'Created',
      value: '2026-01-01T00:00:00Z',
    })).toBe(true);
  });

  it('matches overview rows by fact key and label', () => {
    expect(isOverviewEssentialRow({ fact_key: 'sku', label: 'SKU', value: 'Premium_LRS' })).toBe(true);
    expect(isOverviewEssentialRow({ fact_key: 'diskState', label: 'Disk state', value: 'Attached' })).toBe(true);
    expect(isOverviewEssentialRow({
      fact_key: 'supportsHttpsTrafficOnly',
      label: 'Supports Https Traffic Only',
      value: true,
    })).toBe(false);
  });

  it('normalizes essentials match keys across formats', () => {
    expect(essentialsRowMatchKey({ key: 'resource-group', label: 'Resource group' })).toBe('resourcegroup');
    expect(essentialsRowMatchKey({ fact_key: 'resourceGroup', label: 'Resource group' })).toBe('resourcegroup');
    expect(essentialsRowMatchKey({ fact_key: 'diskSizeGB', label: 'Disk Size GB' })).toBe('disksizegb');
  });

  it('maps AKS essentials variants to one canonical key', () => {
    expect(essentialsRowMatchKey({ key: 'aks-node-auto-provisioning', label: 'Node auto provisioning' })).toBe('nodeautoprovisioning');
    expect(essentialsRowMatchKey({ fact_key: 'node_auto_provisioning', label: 'Node auto provisioning' })).toBe('nodeautoprovisioning');
    expect(essentialsRowMatchKey({ fact_key: 'nodeProvisioningProfile', label: 'Node provisioning profile' })).toBe('nodeautoprovisioning');
    expect(essentialsRowMatchKey({ key: 'aks-node-pools', label: 'Node pools' })).toBe('poolcount');
    expect(essentialsRowMatchKey({ fact_key: 'pool_count', label: 'Node pool count' })).toBe('poolcount');
    expect(essentialsRowMatchKey({ key: 'nodes', label: 'Nodes' })).toBe('nodecount');
    expect(essentialsRowMatchKey({ fact_key: 'node_count', label: 'Total node count' })).toBe('nodecount');
  });

  it('dedupeEssentialRows keeps the first row per canonical key', () => {
    const rows = dedupeEssentialRows([
      { key: 'node_auto_provisioning', label: 'Node auto provisioning', value: 'Enabled' },
      { fact_key: 'nodeProvisioningProfile', label: 'Node auto provisioning', value: 'Enabled' },
      { key: 'sku', label: 'SKU', value: 'Free' },
      { fact_key: 'sku', label: 'SKU', value: 'Free' },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row.label)).toEqual(['Node auto provisioning', 'SKU']);
  });
});

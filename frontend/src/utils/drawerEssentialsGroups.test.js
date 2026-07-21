import {
  classifyEssentialRow,
  organizeEssentialsIntoGroups,
  packEssentialGroups,
} from './drawerEssentialsGroups';

describe('drawerEssentialsGroups', () => {
  test('classifyEssentialRow maps inventory fields to groups', () => {
    expect(classifyEssentialRow({ key: 'type', label: 'Type' })).toBe('identity');
    expect(classifyEssentialRow({ key: 'status', label: 'Status' })).toBe('status');
    expect(classifyEssentialRow({ key: 'sku', label: 'SKU' })).toBe('configuration');
    expect(classifyEssentialRow({ key: 'managedby', label: 'Managed by' })).toBe('networking');
    expect(classifyEssentialRow({ key: 'access-tier', label: 'Access tier' })).toBe('cost');
  });

  test('organizeEssentialsIntoGroups omits empty groups and merges sections', () => {
    const groups = organizeEssentialsIntoGroups({
      rows: [
        { key: 'type', label: 'Type', value: 'Virtual machine' },
        { key: 'status', label: 'Status', value: 'Running' },
        { key: 'sku', label: 'SKU', value: 'Standard_D2s_v3' },
      ],
      propertySections: [
        {
          id: 'prop:general',
          label: 'General',
          rows: [
            { key: 'supportsHttpsTrafficOnly', label: 'Supports HTTPS traffic only', value: 'Yes' },
          ],
        },
      ],
      technicalPropertySections: [],
    });

    expect(groups.map((group) => group.id)).toEqual(
      expect.arrayContaining(['identity__status', 'configuration']),
    );
    const identityStatus = groups.find((group) => group.id === 'identity__status');
    expect(identityStatus?.rows.some((row) => row.label === 'Type')).toBe(true);
    expect(identityStatus?.rows.some((row) => row.label === 'Status')).toBe(true);
    expect(groups.find((group) => group.id === 'configuration')?.rows[0]?.label).toBe('SKU');
    expect(groups.find((group) => group.id === 'configuration')?.rows.some((row) => row.label.includes('HTTPS'))).toBe(true);
    expect(groups.some((group) => group.id === 'networking')).toBe(false);
  });

  test('organizeEssentialsIntoGroups inlines nested ARM sections as group cards', () => {
    const groups = organizeEssentialsIntoGroups({
      rows: [{ key: 'sku', label: 'SKU', value: 'Standard' }],
      technicalPropertySections: [
        {
          id: 'prop:httplisteners',
          label: 'Http listeners',
          rows: [
            { key: 'listener-1', label: 'Listener 1', value: '443' },
            { key: 'listener-2', label: 'Listener 2', value: '80' },
          ],
        },
      ],
    });

    expect(groups.some((group) => group.label === 'Http listeners')).toBe(true);
    expect(groups.find((group) => group.label === 'Http listeners')?.rows).toHaveLength(2);
  });

  test('packEssentialGroups merges single-row standard groups', () => {
    const packed = packEssentialGroups([
      { id: 'identity', label: 'Identity', rows: [{ key: 'location', label: 'Location', value: 'East US' }] },
      { id: 'status', label: 'Status', rows: [{ key: 'status', label: 'Status', value: 'Running' }] },
      { id: 'configuration', label: 'Configuration', rows: [
        { key: 'sku', label: 'SKU', value: 'Standard' },
        { key: 'tier', label: 'Tier', value: 'Premium' },
      ] },
    ]);

    expect(packed).toHaveLength(2);
    expect(packed[0].label).toContain('Identity');
    expect(packed[0].rows).toHaveLength(2);
    expect(packed[1].id).toBe('configuration');
  });

  test('packEssentialGroups marks resource ID groups as full width', () => {
    const packed = packEssentialGroups([
      {
        id: 'identity',
        label: 'Identity',
        rows: [{ key: 'resource-id', label: 'Resource ID', value: '/subscriptions/foo' }],
      },
    ]);

    expect(packed[0].spanFull).toBe(true);
  });

  test('organizeEssentialsIntoGroups dedupes rows with equivalent canonical keys', () => {
    const groups = organizeEssentialsIntoGroups({
      rows: [
        { key: 'node_auto_provisioning', label: 'Node auto provisioning', value: 'Enabled' },
        { fact_key: 'node_auto_provisioning', label: 'Node auto provisioning', value: 'Enabled' },
        { key: 'sku', label: 'SKU', value: 'Free' },
      ],
      propertySections: [
        {
          id: 'prop:general',
          label: 'General',
          rows: [
            { fact_key: 'kubernetesVersion', label: 'Kubernetes version', value: '1.29.2' },
            { fact_key: 'kubernetes_version', label: 'Version', value: '1.29.2' },
          ],
        },
      ],
    });

    const allLabels = groups.flatMap((group) => group.rows.map((row) => row.label));
    expect(allLabels.filter((label) => label === 'Node auto provisioning')).toHaveLength(1);
    expect(allLabels.filter((label) => /version/i.test(label))).toHaveLength(1);
  });
});

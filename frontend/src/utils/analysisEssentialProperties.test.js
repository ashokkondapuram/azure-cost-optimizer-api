import {
  getAnalysisFieldsForType,
  isAnalysisEssentialRow,
  partitionAnalysisEssentialRows,
} from './analysisEssentialProperties';

describe('analysisEssentialProperties', () => {
  test('core identity fields are always essential', () => {
    expect(isAnalysisEssentialRow({ key: 'status', label: 'Status' }, { canonicalType: 'compute/vm' })).toBe(true);
    expect(isAnalysisEssentialRow({ key: 'sku', label: 'SKU' }, { canonicalType: 'compute/disk' })).toBe(true);
    expect(isAnalysisEssentialRow({ key: 'type', label: 'Type' }, { canonicalType: 'storage/account' })).toBe(true);
  });

  test('compute/disk analysis fields from optimization rules', () => {
    const spec = getAnalysisFieldsForType('compute/disk');
    expect(spec.factKeys).toEqual(expect.arrayContaining([
      'disk_state', 'size_gb', 'provisioned_iops', 'managed_by', 'sku',
    ]));

    expect(isAnalysisEssentialRow(
      { fact_key: 'diskSizeGB', label: 'Disk size (GB)', value: '128' },
      { canonicalType: 'compute/disk' },
    )).toBe(true);
    expect(isAnalysisEssentialRow(
      { fact_key: 'encryption', label: 'Encryption', value: 'Enabled' },
      { canonicalType: 'compute/disk' },
    )).toBe(false);
  });

  test('compute/vm analysis fields exclude verbose ARM metadata', () => {
    expect(isAnalysisEssentialRow(
      { fact_key: 'hardwareProfile.vmSize', label: 'VM size', value: 'Standard_D2s_v3' },
      { canonicalType: 'compute/vm' },
    )).toBe(true);
    expect(isAnalysisEssentialRow(
      { fact_key: 'osProfile.computerName', label: 'Computer name', value: 'vm01' },
      { canonicalType: 'compute/vm' },
    )).toBe(false);
  });

  test('storage/account keeps tier/kind/replication, drops governance-only fields', () => {
    expect(isAnalysisEssentialRow(
      { fact_key: 'accessTier', label: 'Access tier', value: 'Hot' },
      { canonicalType: 'storage/account' },
    )).toBe(true);
    expect(isAnalysisEssentialRow(
      { fact_key: 'supportsHttpsTrafficOnly', label: 'Supports HTTPS traffic only', value: 'Yes' },
      { canonicalType: 'storage/account' },
    )).toBe(false);
  });

  test('partitionAnalysisEssentialRows splits overview from overflow', () => {
    const { essential, overflow } = partitionAnalysisEssentialRows([
      { key: 'sku', label: 'SKU', value: 'Premium_LRS' },
      { fact_key: 'diskSizeGB', label: 'Disk size (GB)', value: '512' },
      { fact_key: 'shareInfo', label: 'Share info', value: '[]' },
    ], { canonicalType: 'compute/disk' });

    expect(essential.map((row) => row.label)).toEqual(expect.arrayContaining(['SKU', 'Disk size (GB)']));
    expect(overflow.map((row) => row.label)).toEqual(['Share info']);
  });
});

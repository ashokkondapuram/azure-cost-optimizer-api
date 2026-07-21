import { exportAllResourcesCSV, exportRecommendationsCSV } from './exporters';
import { downloadCsv, toCsv } from './csvExport';

jest.mock('./csvExport', () => ({
  downloadCsv: jest.fn(),
  toCsv: jest.requireActual('./csvExport').toCsv,
}));

describe('exporters', () => {
  beforeEach(() => {
    downloadCsv.mockClear();
  });

  test('exportAllResourcesCSV builds resource rows', () => {
    exportAllResourcesCSV([
      {
        name: 'vm-01',
        resource_group: 'rg-prod',
        location: 'eastus',
        sku: 'Standard_D2s_v3',
        state: 'running',
        monthlyCostBilling: 42.5,
        id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-01',
      },
    ], 'vms.csv');

    expect(downloadCsv).toHaveBeenCalledWith('vms.csv', expect.stringContaining('vm-01'));
    expect(downloadCsv.mock.calls[0][1]).toContain('rg-prod');
    expect(downloadCsv.mock.calls[0][1]).toContain('42.5');
  });

  test('exportRecommendationsCSV builds finding rows', () => {
    exportRecommendationsCSV([
      {
        rule_name: 'DISK_UNUSED',
        severity: 'HIGH',
        category: 'cost',
        status: 'open',
        resource_name: 'disk-01',
        resource_group: 'rg-dev',
        estimated_savings_usd: 12,
        recommendation: 'Delete unused disk',
      },
    ]);

    const csv = downloadCsv.mock.calls[0][1];
    expect(csv).toContain('DISK_UNUSED');
    expect(csv).toContain('disk-01');
    expect(csv).toContain('Delete unused disk');
  });

  test('toCsv handles empty arrays', () => {
    expect(toCsv([])).toBe('');
  });
});

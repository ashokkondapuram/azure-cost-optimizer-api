import { matchesActionCentreResourcePage, matchesActionCentreCategory } from './actionCentreResourceFilter';
import { RESOURCE_PAGES } from '../config/appRegistry';

describe('actionCentreResourceFilter', () => {
  test('matches canonical resource types from count keys', () => {
    const webApp = {
      id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.web/sites/app1',
      type: 'appservice/webapp',
    };
    expect(matchesActionCentreResourcePage(webApp, RESOURCE_PAGES.appservices)).toBe(true);
    expect(matchesActionCentreResourcePage(webApp, RESOURCE_PAGES.disks)).toBe(false);
  });

  test('matches ARM provider types via path hints', () => {
    const sqlServer = {
      id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.sql/servers/sql1',
      type: 'microsoft.sql/servers',
    };
    expect(matchesActionCentreResourcePage(sqlServer, RESOURCE_PAGES.sql)).toBe(true);
  });

  test('disambiguates disks from snapshots and VMs from VMSS', () => {
    const disk = {
      id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d1',
      type: 'compute/disk',
    };
    const snapshot = {
      id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/snapshots/s1',
      type: 'compute/snapshot',
    };
    const vm = {
      id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1',
      type: 'compute/vm',
    };
    const vmss = {
      id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachinescalesets/ss1',
      type: 'compute/vmss',
    };

    expect(matchesActionCentreResourcePage(disk, RESOURCE_PAGES.disks)).toBe(true);
    expect(matchesActionCentreResourcePage(snapshot, RESOURCE_PAGES.disks)).toBe(false);
    expect(matchesActionCentreResourcePage(snapshot, RESOURCE_PAGES.snapshots)).toBe(true);
    expect(matchesActionCentreResourcePage(vm, RESOURCE_PAGES.vms)).toBe(true);
    expect(matchesActionCentreResourcePage(vmss, RESOURCE_PAGES.vms)).toBe(false);
  });

  test('matches per-type platform services', () => {
    const workspace = {
      id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.operationalinsights/workspaces/la1',
      type: 'monitoring/loganalytics',
    };
    expect(matchesActionCentreResourcePage(workspace, RESOURCE_PAGES.loganalytics)).toBe(true);
    expect(matchesActionCentreResourcePage(workspace, RESOURCE_PAGES.appinsights)).toBe(false);
  });

  test('category filter falls back to row category when analysis exists', () => {
    const row = { category: 'COMPUTE', analysisFindingsCount: 2 };
    const rec = { findings: [], hasRecommendations: true };
    expect(matchesActionCentreCategory(row, rec, 'COMPUTE')).toBe(true);
    expect(matchesActionCentreCategory(row, rec, 'STORAGE')).toBe(false);
  });
});

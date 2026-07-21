import {
  validateAppRegistry,
  RESOURCE_PAGES,
  RESOURCE_NAV_CATALOG,
  NAV_RESOURCE_GROUPS,
  DASHBOARD_SECTIONS,
  visibleNavGroups,
  visibleDashboardItems,
  hasResourceInventory,
  hasResourceCost,
  isResourceVisibleInUi,
  isResourceVisibleOnDashboard,
  syncTypesForNavGroup,
  syncTypesForResourceIds,
  categoryResourceCount,
  isSystemNavVisible,
  systemNavItems,
  ADVANCED_NAV_GROUPS,
} from './appRegistry';
import { ROUTE_ICON_KEYS, validateIconRegistry, ICON_COMPONENTS } from './azureIconRegistry';

describe('appRegistry', () => {
  it('has no registry validation errors', () => {
    const errors = validateAppRegistry();
    expect(errors).toEqual([]);
  });

  it('maps every resource page to a route icon', () => {
    for (const page of Object.values(RESOURCE_PAGES)) {
      expect(ROUTE_ICON_KEYS[page.path]).toBeTruthy();
      expect(ICON_COMPONENTS[ROUTE_ICON_KEYS[page.path]]).toBeTruthy();
    }
  });

  it('keeps resource catalog aligned with resource pages', () => {
    const navIds = new Set(RESOURCE_NAV_CATALOG.flatMap((g) => g.resourceIds));
    const pageIds = new Set(
      Object.keys(RESOURCE_PAGES).filter((id) => id !== 'cost-resources'),
    );
    for (const id of pageIds) {
      expect(navIds.has(id)).toBe(true);
    }
  });

  it('references only known resources in dashboard sections', () => {
    for (const section of DASHBOARD_SECTIONS) {
      for (const item of section.items) {
        if (item.type === 'resource') {
          expect(RESOURCE_PAGES[item.id]).toBeDefined();
        }
      }
    }
  });

  it('passes icon registry validation alongside app registry', () => {
    expect(validateIconRegistry()).toEqual([]);
  });

  it('hides per-resource sidebar groups when using unified action centre', () => {
    expect(NAV_RESOURCE_GROUPS).toEqual([]);
    const counts = {
      vms: 3,
      disks: 0,
      vmss: 0,
      aks: 1,
      vnets: 5,
      privateendpoints: 2,
      nsgs: 20,
      nics: 15,
      breakdown: {
        vms: { inventory: 3, has_cost: true, cost_type: 'costed', cost_mtd: 50 },
        aks: { inventory: 1, has_cost: true, cost_type: 'costed', cost_mtd: 10 },
        vnets: { inventory: 5, has_cost: false, cost_type: 'conditional', cost_mtd: 0, findings_count: 0 },
        privateendpoints: { inventory: 2, has_cost: false, cost_type: 'costed', cost_mtd: 0, findings_count: 0 },
        nsgs: { inventory: 20, has_cost: false, cost_type: 'free', cost_mtd: 0 },
        nics: { inventory: 15, has_cost: false, cost_type: 'free', cost_mtd: 0 },
      },
    };
    expect(visibleNavGroups(counts)).toEqual([]);
  });

  it('builds category sync types from visible resource ids only', () => {
    const types = syncTypesForResourceIds(['vms', 'privateendpoints']);
    expect(types).toContain('compute/vm');
    expect(types).toContain('network/privateendpoint');
    expect(types).not.toContain('network/nsg');
    expect(types).not.toContain('network/nic');
  });

  it('builds category sync types from nav groups', () => {
    const computeTypes = syncTypesForNavGroup('compute');
    expect(computeTypes).toContain('compute/vm');
    expect(computeTypes).not.toContain('compute/vmss');
    expect(computeTypes).not.toContain('compute/disk');
    expect(computeTypes).not.toContain('compute/snapshot');

    const storageTypes = syncTypesForNavGroup('storage');
    expect(storageTypes).toContain('compute/disk');
    expect(storageTypes).toContain('compute/snapshot');
    expect(storageTypes).toContain('storage/account');
  });

  it('sums category resource counts from inventory keys', () => {
    const compute = RESOURCE_NAV_CATALOG.find((g) => g.id === 'compute');
    expect(categoryResourceCount(compute, { vms: 2, vmss: 0, disks: 3 })).toBe(2);

    const storage = RESOURCE_NAV_CATALOG.find((g) => g.id === 'storage');
    expect(categoryResourceCount(storage, { disks: 3, snapshots: 1, storage: 2 })).toBe(6);
  });

  it('respects hidden and always-show flags for inventory visibility', () => {
    expect(isResourceVisibleInUi(RESOURCE_PAGES['cost-resources'], { cost_resources: 5 })).toBe(false);
    expect(hasResourceInventory({ vms: 0 }, 'vms')).toBe(false);
    expect(hasResourceInventory({ vms: 2 }, 'vms')).toBe(true);
  });

  it('hides free resource types from dashboard tiles', () => {
    const counts = {
      vms: 5,
      privateendpoints: 10,
      nsgs: 20,
      breakdown: {
        vms: { inventory: 5, has_cost: true, cost_type: 'costed', cost_mtd: 120 },
        privateendpoints: { inventory: 10, has_cost: false, cost_type: 'costed', cost_mtd: 0, findings_count: 0 },
        nsgs: { inventory: 20, has_cost: false, cost_type: 'free', cost_mtd: 0 },
      },
    };
    expect(hasResourceCost(counts, 'vms')).toBe(true);
    expect(hasResourceCost(counts, 'privateendpoints')).toBe(false);
    expect(hasResourceCost(counts, 'nsgs')).toBe(false);
    expect(isResourceVisibleOnDashboard(RESOURCE_PAGES.vms, counts)).toBe(true);
    expect(isResourceVisibleOnDashboard(RESOURCE_PAGES.privateendpoints, counts)).toBe(false);
    expect(isResourceVisibleOnDashboard(RESOURCE_PAGES.nsgs, counts)).toBe(false);

    const networkSection = DASHBOARD_SECTIONS.find((s) => s.id === 'network');
    const visible = visibleDashboardItems(networkSection, counts);
    const ids = visible.map((item) => item.link);
    expect(ids).not.toContain('/privateendpoints');
    expect(ids).not.toContain('/nsgs');
  });

  it('hides free types from sidebar badges when breakdown is present', () => {
    const networking = RESOURCE_NAV_CATALOG.find((g) => g.id === 'networking');
    const counts = {
      vms: 1,
      nsgs: 40,
      privateendpoints: 5,
      breakdown: {
        vms: { inventory: 1, has_cost: true, cost_type: 'costed', cost_mtd: 25 },
        nsgs: { inventory: 40, has_cost: false, cost_type: 'free' },
        privateendpoints: { inventory: 5, has_cost: true, cost_type: 'costed', cost_mtd: 12 },
      },
    };
    expect(categoryResourceCount(networking, counts, { costOnly: true })).toBe(5);
    expect(categoryResourceCount(networking, counts)).toBe(45);
  });

  it('hides system nav for viewers', () => {
    expect(isSystemNavVisible(false)).toBe(false);
    expect(isSystemNavVisible(true)).toBe(true);
    expect(systemNavItems(false)).toEqual([]);
    expect(systemNavItems(true).some((item) => item.path === '/history')).toBe(true);
    expect(systemNavItems(true).some((item) => item.path === '/settings')).toBe(true);
  });

  it('registers cost anomaly page in advanced nav', () => {
    const insights = ADVANCED_NAV_GROUPS.find((g) => g.id === 'advanced-insights');
    expect(insights?.items.some((item) => item.path === '/anomaly-detector')).toBe(true);
  });
});

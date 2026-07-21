import {
  filterDrawerFindings,
  getDrawerCapabilities,
  isBillingOrCommitmentResource,
  isUuidLike,
  resolveResourceDisplayName,
  buildDrawerSections,
  DRAWER_SECTION_IDS,
  hasCostDriversContent,
  hasTrendsContent,
} from './drawerCapabilities';

describe('drawerCapabilities', () => {
  const savingsPlan = {
    id: '/providers/microsoft.billingbenefits/savingsplanorders/2a84fff5-ba5d-4c09-8c09-948167c83668',
    name: '2a84fff5-ba5d-4c09-8c09-948167c83668',
    type: 'microsoft.billingbenefits/savingsplanorders',
    azureServiceName: 'Unassigned',
  };

  test('detects savings plan orders', () => {
    expect(isBillingOrCommitmentResource(savingsPlan)).toBe(true);
  });

  test('resolves friendly display name for UUID resources', () => {
    expect(resolveResourceDisplayName(savingsPlan)).toMatch(/2a84fff5/);
    expect(resolveResourceDisplayName(savingsPlan)).not.toBe(savingsPlan.name);
  });

  test('filters inappropriate spend findings for billing resources', () => {
    const findings = [
      { id: 1, rule_id: 'COST_HIGH_SPEND_REVIEW', rule_name: 'High monthly spend review' },
      { id: 2, rule_id: 'OTHER', rule_name: 'Other' },
    ];
    const filtered = filterDrawerFindings(findings, savingsPlan);
    expect(filtered).toHaveLength(1);
    expect(filtered[0].rule_id).toBe('OTHER');
  });

  test('hides workload sections for billing resources', () => {
    const caps = getDrawerCapabilities(savingsPlan, {
      rid: savingsPlan.id,
      subscription: 'sub-1',
    });
    expect(caps.billing).toBe(true);
    expect(caps.showMetrics).toBe(false);
    expect(caps.showAnalysis).toBe(false);
    expect(caps.showAdvisor).toBe(false);
    expect(caps.overviewNote).toMatch(/Savings planner/i);
  });

  test('isUuidLike', () => {
    expect(isUuidLike('2a84fff5-ba5d-4c09-8c09-948167c83668')).toBe(true);
    expect(isUuidLike('vm-prod-01')).toBe(false);
  });
});

describe('drawer section registry', () => {
  const vm = {
    id: '/subscriptions/sub-1/resourcegroups/rg-prod/providers/microsoft.compute/virtualmachines/vm-web-01',
    name: 'vm-web-01',
    type: 'microsoft.compute/virtualmachines',
    location: 'eastus',
    tags: { environment: 'prod' },
  };

  const metricsWithDrivers = {
    cost_driver_mapping: { cost_drivers: [{ kind: 'metric', fact_key: 'avg_cpu_pct' }] },
    metrics: [{ fact_key: 'avg_cpu_pct', trigger: true, value: 12 }],
    derived: [],
  };

  test('buildDrawerSections orders tabs: overview → findings → metrics → cost drivers → trends', () => {
    const caps = getDrawerCapabilities(vm, {
      rid: vm.id,
      subscription: 'sub-1',
    });
    const sections = buildDrawerSections({
      resolved: { rid: vm.id },
      capabilities: caps,
      displayFindings: [{ id: 1, rule_id: 'VM_OVERSIZE', pillar: 'cost' }],
      displayTags: vm.tags,
      drawerResource: vm,
      bundleMetrics: metricsWithDrivers,
      bundleAnalysis: {
        trends: { cpu_trend: { slope: 'increasing' } },
      },
      hasAnalysisInsights: true,
      hasCostSection: true,
      hasPropertiesSection: true,
      totalCost: 120,
    });

    const ids = sections.map((s) => s.id);
    expect(ids).toEqual([
      DRAWER_SECTION_IDS.overview,
      DRAWER_SECTION_IDS.properties,
      DRAWER_SECTION_IDS.findings,
      DRAWER_SECTION_IDS.metrics,
      DRAWER_SECTION_IDS.costDrivers,
      DRAWER_SECTION_IDS.trends,
      DRAWER_SECTION_IDS.cost,
      DRAWER_SECTION_IDS.analysis,
      DRAWER_SECTION_IDS.tags,
    ]);
  });

  test('buildDrawerSections places findings immediately after overview', () => {
    const caps = getDrawerCapabilities(vm, {
      rid: vm.id,
      subscription: 'sub-1',
    });
    const sections = buildDrawerSections({
      resolved: { rid: vm.id },
      capabilities: caps,
      displayFindings: [{ id: 1 }],
      displayTags: vm.tags,
      drawerResource: vm,
      bundleMetrics: metricsWithDrivers,
      bundleAnalysis: {},
    });
    const ids = sections.map((s) => s.id);
    expect(ids.indexOf(DRAWER_SECTION_IDS.findings)).toBe(1);
    expect(ids.indexOf(DRAWER_SECTION_IDS.findings)).toBeLessThan(ids.indexOf(DRAWER_SECTION_IDS.metrics));
  });

  test('buildDrawerSections places cost drivers after metrics and before trends', () => {
    const caps = getDrawerCapabilities(vm, {
      rid: vm.id,
      subscription: 'sub-1',
    });
    const sections = buildDrawerSections({
      resolved: { rid: vm.id },
      capabilities: caps,
      displayFindings: [],
      displayTags: vm.tags,
      drawerResource: vm,
      bundleMetrics: metricsWithDrivers,
      bundleAnalysis: {},
      advisorRecommendations: [{ id: 'a1' }],
      proposedActions: [{ id: 'p1' }],
    });
    const ids = sections.map((s) => s.id);
    expect(ids.indexOf(DRAWER_SECTION_IDS.costDrivers)).toBeGreaterThan(ids.indexOf(DRAWER_SECTION_IDS.metrics));
    expect(ids.indexOf(DRAWER_SECTION_IDS.costDrivers)).toBeLessThan(ids.indexOf(DRAWER_SECTION_IDS.trends));
    expect(ids.indexOf(DRAWER_SECTION_IDS.trends)).toBeLessThan(ids.indexOf(DRAWER_SECTION_IDS.actions));
  });

  test('hasCostDriversContent detects drivers and triggers', () => {
    expect(hasCostDriversContent(metricsWithDrivers)).toBe(true);
    expect(hasCostDriversContent({ metrics: [], derived: [] })).toBe(false);
  });

  test('hasTrendsContent is true when analysis trends exist', () => {
    const caps = getDrawerCapabilities(vm, { rid: vm.id, subscription: 'sub-1' });
    expect(hasTrendsContent({
      capabilities: caps,
      bundleAnalysis: { trends: { memory_trend: { slope: 'stable' } } },
      bundleMetrics: null,
      resource: vm,
    })).toBe(true);
  });

  test('hasTrendsContent is true for application gateway with configured monitor metrics', () => {
    const agw = {
      id: '/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.network/applicationgateways/agw1',
      type: 'microsoft.network/applicationgateways',
      properties: {
        backendAddressPools: [{ name: 'pool1' }],
        probes: [{ name: 'probe1' }, { name: 'probe2' }],
      },
    };
    const caps = getDrawerCapabilities(agw, {
      rid: agw.id,
      subscription: 'sub-1',
      apiPath: '/resources/appgateways',
    });
    expect(caps.showMetrics).toBe(false);
    expect(hasTrendsContent({
      capabilities: caps,
      bundleAnalysis: null,
      bundleMetrics: null,
      resource: agw,
      canonicalType: 'network/appgateway',
    })).toBe(true);
  });

  test('buildDrawerSections does not crash when metrics bundle is not loaded', () => {
    const caps = getDrawerCapabilities(vm, {
      rid: vm.id,
      subscription: 'sub-1',
    });
    expect(() => buildDrawerSections({
      resolved: { rid: vm.id },
      capabilities: caps,
      displayFindings: [],
      displayTags: vm.tags,
      drawerResource: vm,
      bundleMetrics: undefined,
      bundleAnalysis: {},
      bundlePending: true,
    })).not.toThrow();

    const sections = buildDrawerSections({
      resolved: { rid: vm.id },
      capabilities: caps,
      displayFindings: [],
      displayTags: vm.tags,
      drawerResource: vm,
      bundleMetrics: undefined,
      bundleAnalysis: {},
      bundlePending: true,
    });
    const costDrivers = sections.find((s) => s.id === DRAWER_SECTION_IDS.costDrivers);
    expect(costDrivers).toBeDefined();
    expect(costDrivers.badge).toBeUndefined();
  });

  test('billing resources omit workload tabs', () => {
    const savingsPlan = {
      id: '/providers/microsoft.billingbenefits/savingsplanorders/uuid',
      type: 'microsoft.billingbenefits/savingsplanorders',
    };
    const caps = getDrawerCapabilities(savingsPlan, {
      rid: savingsPlan.id,
      subscription: 'sub-1',
    });
    const sections = buildDrawerSections({
      resolved: { rid: savingsPlan.id },
      capabilities: caps,
      displayFindings: [],
      displayTags: {},
      drawerResource: savingsPlan,
      bundleMetrics: metricsWithDrivers,
      bundleAnalysis: { trends: { cpu_trend: {} } },
      hasCostSection: false,
    });
    const ids = sections.map((s) => s.id);
    expect(ids).not.toContain(DRAWER_SECTION_IDS.costDrivers);
    expect(ids).not.toContain(DRAWER_SECTION_IDS.trends);
  });
});

import {
  buildInsightData,
  buildPropertyGroups,
  buildRationale,
  buildEvidenceRows,
  filterCanvasPropertyGroups,
  filterAssessmentPropertyGroups,
  filterAssessmentPropertyItems,
  getVisibleCanvasSections,
  isAksAllowedProperty,
  isAssessmentProperty,
  buildCanvasNodePools,
  buildCanvasInstances,
  buildCanvasMetrics,
  pickPrimaryEvidenceMetric,
  dedupePropertyGroupsByLabel,
  dedupePropertyItemsByLabel,
  normalizePropertyLabelForDedupe,
  organizePropertyGroupsForDisplay,
  organizeDrawerPropertyGroupsForDisplay,
  resolveCanvasPropertyGroups,
  INSIGHT_PROFILES,
} from './insightCanvasUtils';

describe('buildInsightData', () => {
  test('coerces powerState objects to display text', () => {
    const data = buildInsightData({
      finding: {
        severity: { code: 'HIGH' },
        category: { code: 'COMPUTE' },
        rule_id: { code: 'DISK_OVERSIZE' },
        detail: 'Reduce disk tier',
        resource_name: 'disk-01',
      },
      row: {
        name: 'disk-01',
        properties: {
          powerState: { code: 'PowerState/running' },
          sku: { name: 'Premium_LRS', tier: 'Premium' },
        },
      },
      actions: [],
    });

    expect(data.state).toBe('running');
    expect(data.severity).toBe('High');
    expect(data.category).toBe('Compute');
    expect(data.rule).toBe('DISK_OVERSIZE');
    expect(data.sku.current.name).toBe('Premium_LRS');
  });

  test('builds structured evidence groups instead of raw key:value lines', () => {
    const finding = {
      severity: 'high',
      category: 'tier',
      rule_id: 'DISK_OVERSIZE_EXTENDED',
      detail: 'Downgrade to Standard SSD based on low I/O.',
      evidence: {
        summary: 'Disk I/O is well below provisioned capacity.',
        checks: [
          {
            signal: 'Peak IOPS utilization',
            value: 8,
            threshold: '< 30%',
            passed: true,
            fact_key: 'disk_iops_utilization_pct',
          },
          {
            signal: 'Queue depth average',
            value: 0.1,
            threshold: '< 1',
            passed: true,
          },
        ],
        optimization_metrics: {
          performance: [
            {
              id: 'disk_iops_utilization_pct',
              label: 'Peak IOPS utilization',
              formatted: '8%',
              value: 8,
              unit: '%',
              status: 'low',
            },
          ],
          cost: [
            { id: 'mtd_cost', label: 'Month-to-date cost', formatted: '$42.00', value: 42 },
          ],
        },
      },
    };

    const data = buildInsightData({
      finding,
      row: {
        name: 'disk-01',
        id: '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-01',
        type: 'Microsoft.Compute/disks',
        properties: { diskState: 'Attached', sku: { name: 'Premium_LRS' } },
        metrics: { disk_iops_utilization_pct: 8 },
      },
      actions: [],
    });

    expect(data.rationale.length).toBeGreaterThan(0);
    expect(data.profileType).toBe('disk');
    expect(data.ruleEvidence.length).toBeGreaterThan(0);
    expect(data.ruleEvidence.some((r) => /iops utilization/i.test(r.label))).toBe(true);
    expect(data.ruleEvidence.every((r) => !String(r.label).toLowerCase().includes('assessment file'))).toBe(true);
    expect(data.evidenceGroups).toEqual([]);
    expect(data.evidenceOverflowCount).toBe(0);
    expect(data.metrics.some((m) => m.label === 'IOPS utilization')).toBe(true);
  });

  test('disk finding with inventory-only evidence does not dump threshold config rows', () => {
    const finding = {
      severity: 'high',
      category: 'tier',
      rule_id: 'DISK_OVERSIZE_EXTENDED',
      resource_id: '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-01',
      evidence: {
        assessment_file: 'disk-assessment.json',
        data_quality: 'inventory_only',
        disk_idle_min_size_gb: 128,
        disk_io_idle_bps: 1024,
        creationData: { createOption: 'Copy' },
        exclude_inventory_facts: true,
        evidence_rows: [
          {
            signal: 'disk_iops_utilization_pct',
            label: 'Disk IOPS utilization',
            value: '8%',
            threshold: '< 50%',
            period: '7d',
            pillar: 'performance',
            status: 'pass',
          },
        ],
      },
    };

    const rows = buildEvidenceRows(finding);
    expect(rows.groups.length).toBeGreaterThan(0);
    expect(rows.groups.flatMap((g) => g.rows).every((r) => !/assessment file|disk idle/i.test(r.label))).toBe(true);
    expect(rows.overflowCount).toBe(0);

    const data = buildInsightData({
      finding,
      row: {
        id: finding.resource_id,
        name: 'disk-01',
        type: 'Microsoft.Compute/disks',
        properties: { diskState: 'Attached' },
      },
      actions: [],
    });
    expect(data.ruleEvidence).toHaveLength(1);
    expect(data.ruleEvidence[0].label).toBe('Disk IOPS utilization');
  });

  test('buildInsightData merges assessment_properties for disk insight', () => {
    const finding = {
      severity: 'high',
      rule_id: 'DISK_OVERSIZE_EXTENDED',
      resource_id: '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-01',
      estimated_savings_usd: 30,
    };

    const data = buildInsightData({
      finding,
      row: {
        id: finding.resource_id,
        name: 'disk-01',
        type: 'Microsoft.Compute/disks',
        sku: 'Premium_LRS',
        properties: {},
        assessment_properties: {
          diskSizeGB: '512',
          diskState: 'Attached',
        },
        metrics: { disk_iops_utilization_pct: 8 },
      },
      actions: [],
    });

    expect(data.profileType).toBe('disk');
    expect(data.propertyGroups.some((g) => g.items.some((i) => i.label === 'Disk size' && i.value === '512 GB'))).toBe(true);
  });

  test('builds property groups from billed resource probe payload', () => {
    const groups = buildPropertyGroups({
      resource: {
        id: '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-01',
        name: 'disk-01',
        type: 'Microsoft.Compute/disks',
        location: 'canadacentral',
        resourceGroup: 'rg-apps',
        sku: 'Premium_LRS',
        state: 'Attached',
        properties: {
          diskSizeGB: 128,
          diskState: 'Attached',
          managedBy: '/subscriptions/sub/.../virtualMachines/vm-web-02',
          encryption: { type: 'EncryptionAtRestWithPlatformKey' },
          timeCreated: '2024-03-12T10:00:00Z',
        },
      },
    });

    expect(groups.length).toBeGreaterThan(0);
    const allItems = groups.flatMap((g) => g.items);
    expect(allItems.some((i) => /managed by|attached to/i.test(i.label))).toBe(true);
    expect(allItems.some((i) => /created/i.test(i.label))).toBe(true);
    expect(allItems.every((i) => !String(i.value).includes('diskSizeGB'))).toBe(true);
    expect(allItems.every((i) => !/resource id/i.test(i.label))).toBe(true);
    expect(allItems.some((i) => i.label === 'Disk size')).toBe(true);
  });

  test('canvasPropertyGroups keeps lifecycle and connectivity after SKU dedup', () => {
    const data = buildInsightData({
      finding: {
        severity: 'high',
        category: 'tier',
        rule_id: 'DISK_OVERSIZE_EXTENDED',
        detail: 'Downgrade disk tier.',
        resource_name: 'disk-premium-oversize',
        recommended_tier: 'StandardSSD_LRS',
      },
      row: {
        id: '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-premium-oversize',
        name: 'disk-premium-oversize',
        location: 'canadacentral',
        type: 'Microsoft.Compute/disks',
        properties: { sku: { name: 'Premium_LRS' }, diskSizeGB: 256 },
      },
      propertiesPayload: {
        resource: {
          name: 'disk-premium-oversize',
          type: 'Microsoft.Compute/disks',
          location: 'canadacentral',
          properties: {
            diskSizeGB: 256,
            diskState: 'Attached',
            provisioningState: 'Succeeded',
            managedBy: '/subscriptions/sub/.../virtualMachines/vm-web-02',
          },
        },
      },
      metricsData: {
        ok: true,
        derived: [
          { fact_key: 'disk_iops_utilization_pct', stats: { maximum: 8 }, unit: '%' },
        ],
      },
      actions: [],
    });

    expect(data.profileType).toBe('disk');
    expect(data.propertyGroups.length).toBeGreaterThan(0);
    expect(data.canvasPropertyGroups.length).toBeGreaterThan(0);
    expect(data.canvasPropertyGroups.some((g) => g.title === 'Disk')).toBe(true);
    expect(data.sku.current.specs.length).toBeGreaterThan(0);
    expect(data.metrics.some((m) => m.label === 'IOPS utilization')).toBe(true);
    expect(data.sections.indexOf('metrics')).toBeLessThan(data.sections.indexOf('cost'));
    expect(data.sections.indexOf('cost')).toBeLessThan(data.sections.indexOf('recommendation'));
    const labels = data.canvasPropertyGroups.flatMap((g) => g.items.map((i) => i.label));
    expect(labels.some((l) => /attached to/i.test(l))).toBe(true);
    expect(labels.some((l) => l === 'Disk size')).toBe(true);
  });

  test('filterCanvasPropertyGroups falls back when spec filter would empty groups', () => {
    const groups = [{
      title: 'Disk',
      items: [
        { label: 'IOPS', value: '500' },
        { label: 'Provisioning state', value: 'Succeeded' },
      ],
    }];
    const sku = {
      current: {
        name: 'Premium_LRS P10',
        specs: [{ label: 'IOPS', value: '500' }],
      },
    };
    const filtered = filterCanvasPropertyGroups(groups, sku);
    expect(filtered.length).toBeGreaterThan(0);
    expect(filtered.flatMap((g) => g.items).some((i) => i.label === 'Provisioning state')).toBe(true);
  });

  test('resolveCanvasPropertyGroups never returns empty when source has items', () => {
    const groups = [{
      title: 'Configuration',
      items: [{ label: 'Tier', value: 'Premium_LRS' }],
    }];
    const resolved = resolveCanvasPropertyGroups(groups, { current: { name: 'Premium_LRS', specs: [{ label: 'Tier', value: 'Premium_LRS' }] } });
    expect(resolved.length).toBeGreaterThan(0);
  });

  test('organizePropertyGroupsForDisplay flattens categories into one gap-free grid', () => {
    const flat = organizePropertyGroupsForDisplay([
      { title: 'Configuration', items: [{ label: 'Kubernetes version', value: '1.29.4' }] },
      { title: 'Lifecycle', items: [{ label: 'Power state', value: 'Running' }] },
      { title: 'Connectivity', items: [{ label: 'Outbound type', value: 'loadBalancer' }] },
      { title: 'Security', items: [] },
    ]);
    expect(flat).toHaveLength(1);
    expect(flat[0].flat).toBe(true);
    expect(flat[0].items.map((i) => i.label)).toEqual([
      'Kubernetes version',
      'Power state',
      'Outbound type',
    ]);
  });

  test('organizeDrawerPropertyGroupsForDisplay merges groups into one full-width card', () => {
    const flat = organizeDrawerPropertyGroupsForDisplay([
      { id: 'prop:config', label: 'Configuration', rows: [{ key: 'a', label: 'Version', value: '1.29' }] },
      { id: 'prop:status', label: 'Status', rows: [{ key: 'b', label: 'Power state', value: 'Running' }] },
      { id: 'prop:empty', label: 'Empty', rows: [] },
    ]);
    expect(flat).toHaveLength(1);
    expect(flat[0].flat).toBe(true);
    expect(flat[0].spanFull).toBe(true);
    expect(flat[0].rows).toHaveLength(2);
  });

  test('dedupePropertyGroupsByLabel keeps first power state across groups', () => {
    const groups = [
      {
        title: 'Configuration',
        items: [
          { label: 'Power state', value: 'Running' },
          { label: 'Kubernetes version', value: '1.29.4' },
        ],
      },
      {
        title: 'Lifecycle',
        items: [
          { label: 'Power state', value: 'Running' },
          { label: 'State', value: 'Running' },
        ],
      },
      {
        title: 'Agent pool profiles',
        items: [
          { label: 'Power state', value: 'Running' },
        ],
      },
    ];
    const deduped = dedupePropertyGroupsByLabel(groups);
    const powerRows = deduped.flatMap((g) => g.items).filter((i) => /power state|^state$/i.test(i.label));
    expect(powerRows).toHaveLength(1);
    expect(powerRows[0]).toMatchObject({ label: 'Power state', value: 'Running' });
    expect(deduped.flatMap((g) => g.items).filter((i) => i.label === 'Kubernetes version')).toHaveLength(1);
  });

  test('dedupePropertyItemsByLabel aliases status and state to power state', () => {
    const items = dedupePropertyItemsByLabel([
      { label: 'Status', value: 'Running' },
      { label: 'State', value: 'Running' },
      { label: 'Power state', value: 'Running' },
    ]);
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Status');
  });

  test('normalizePropertyLabelForDedupe collapses state variants', () => {
    expect(normalizePropertyLabelForDedupe('Power state')).toBe('power state');
    expect(normalizePropertyLabelForDedupe('State')).toBe('power state');
    expect(normalizePropertyLabelForDedupe('Status')).toBe('power state');
  });

  test('AKS properties allow only cluster-level power state', () => {
    expect(isAksAllowedProperty('Power state', 'powerState')).toBe(true);
    expect(isAksAllowedProperty('Power state', 'agentPoolProfiles.0.powerState')).toBe(false);
    expect(isAksAllowedProperty('Power state', 'networkProfile.loadBalancerProfile.powerState')).toBe(false);
  });

  test('buildInsightData dedupes repeated power state in canvas properties', () => {
    const data = buildInsightData({
      finding: { severity: 'low', category: 'compute', rule_id: 'AKS_IDLE', detail: 'Review cluster.' },
      row: {
        name: 'prod-aks',
        type: 'Microsoft.ContainerService/managedClusters',
        state: 'Running',
        properties: {
          powerState: 'Running',
          kubernetesVersion: '1.29.4',
          agentPoolProfiles: [
            { name: 'system', powerState: 'Running', count: 2 },
          ],
        },
      },
      propertiesPayload: {
        resource: {
          name: 'prod-aks',
          type: 'Microsoft.ContainerService/managedClusters',
          state: 'Running',
          properties: {
            powerState: 'Running',
            kubernetesVersion: '1.29.4',
            agentPoolProfiles: [
              { name: 'system', powerState: 'Running', count: 2 },
            ],
          },
        },
        inventory_properties: [
          { label: 'Power state', fact_key: 'power_state', value: 'Running' },
        ],
      },
      actions: [],
    });

    const labels = data.canvasPropertyGroups.flatMap((g) => g.items.map((i) => i.label));
    const powerCount = labels.filter((l) => normalizePropertyLabelForDedupe(l) === 'power state').length;
    expect(powerCount).toBe(1);
    expect(labels).toContain('Kubernetes version');
  });

  test('isAssessmentProperty excludes ARM IDs and header duplicates for AKS', () => {
    expect(isAssessmentProperty('Resource ID', 'id', 'containers/aks')).toBe(false);
    expect(isAssessmentProperty('Subscription ID', 'subscription_id', 'containers/aks')).toBe(false);
    expect(isAssessmentProperty('Resource group', 'resource_group', 'containers/aks')).toBe(false);
    expect(isAssessmentProperty('Kubernetes version', 'kubernetesVersion', 'containers/aks')).toBe(true);
    expect(isAssessmentProperty('Network plugin', 'networkPlugin', 'containers/aks')).toBe(false);
    expect(isAssessmentProperty('Node auto provisioning', 'node_auto_provisioning', 'containers/aks')).toBe(false);
    expect(isAssessmentProperty('Provisioning state', 'provisioningState', 'containers/aks')).toBe(false);
    expect(isAssessmentProperty('Power state', 'powerState', 'containers/aks')).toBe(true);
    expect(isAssessmentProperty('Outbound type', 'networkProfile.outboundType', 'containers/aks')).toBe(true);
    expect(isAssessmentProperty('Load balancer SKU', 'networkProfile.loadBalancerSku', 'containers/aks')).toBe(true);
    expect(isAssessmentProperty('Mode', 'nodeProvisioningProfile.mode', 'containers/aks')).toBe(true);
    expect(isAssessmentProperty('Mode', 'agentPoolProfiles.0.mode', 'containers/aks')).toBe(false);
  });

  test('isAksAllowedProperty matches only portal-style cluster fields', () => {
    expect(isAksAllowedProperty('Kubernetes version', 'kubernetesVersion')).toBe(true);
    expect(isAksAllowedProperty('Node provisioning profile', 'nodeProvisioningProfile')).toBe(true);
    expect(isAksAllowedProperty('Mode', 'nodeProvisioningProfile.mode')).toBe(true);
    expect(isAksAllowedProperty('Default node pools', 'nodeProvisioningProfile.defaultNodePools')).toBe(true);
    expect(isAksAllowedProperty('Load balancer profile · Effective outbound ips', 'networkProfile.loadBalancerProfile.effectiveOutboundIPs')).toBe(true);
    expect(isAksAllowedProperty('Network plugin', 'networkProfile.networkPlugin')).toBe(false);
    expect(isAksAllowedProperty('Node pools', 'pool_count')).toBe(false);
    expect(isAksAllowedProperty('Nodes', 'node_count')).toBe(false);
  });

  test('filterAssessmentPropertyItems keeps only AKS allowlist rows', () => {
    const items = filterAssessmentPropertyItems([
      { label: 'Kubernetes version', fact_key: 'kubernetesVersion', value: '1.29.4' },
      { label: 'Network plugin', fact_key: 'networkPlugin', value: 'azure' },
      { label: 'Power state', fact_key: 'powerState', value: 'Running' },
      { label: 'Node auto provisioning', fact_key: 'node_auto_provisioning', value: 'Disabled' },
      { label: 'Outbound type', fact_key: 'networkProfile.outboundType', value: 'loadBalancer' },
    ], 'containers/aks');
    const labels = items.map((item) => item.label);
    expect(labels).toEqual(expect.arrayContaining([
      'Kubernetes version',
      'Power state',
      'Outbound type',
    ]));
    expect(labels).not.toContain('Network plugin');
    expect(labels).not.toContain('Node auto provisioning');
    expect(labels.length).toBeLessThanOrEqual(10);
  });

  test('filterAssessmentPropertyGroups removes ARM path values and non-allowlist AKS rows', () => {
    const filtered = filterAssessmentPropertyGroups([{
      title: 'Configuration',
      items: [
        { label: 'Managed by', value: '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-01' },
        { label: 'Cluster resource ID', value: '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks-01' },
        { label: 'Kubernetes version', fact_key: 'kubernetesVersion', value: '1.29.4' },
        { label: 'Network plugin', fact_key: 'networkPlugin', value: 'azure' },
      ],
    }], 'containers/aks');
    const labels = filtered.flatMap((g) => g.items.map((i) => i.label));
    expect(labels).toContain('Kubernetes version');
    expect(labels).not.toContain('Managed by');
    expect(labels).not.toContain('Cluster resource ID');
    expect(labels).not.toContain('Network plugin');
  });

  test('getVisibleCanvasSections uses disk section order from profile', () => {
    const data = {
      insights: null,
      advisor: [],
      trends: [],
      nodePools: [],
      metrics: [{ label: 'IOPS utilization', value: '8%' }],
      instances: [],
      canvasPropertyGroups: [{ title: 'Disk', items: [{ label: 'Disk size', value: '256 GB' }] }],
    };
    const sections = getVisibleCanvasSections(data, INSIGHT_PROFILES.disk);
    expect(sections).toEqual([
      'summary', 'metrics', 'cost', 'recommendation', 'properties', 'tags', 'history',
    ]);
  });

  test('getVisibleCanvasSections orders pools before recommendation for kubernetes', () => {
    const data = {
      insights: null,
      advisor: [],
      trends: [],
      nodePools: [{ name: 'system' }],
      metrics: [{ label: 'CPU', value: '12%' }],
      instances: [],
      canvasPropertyGroups: [{ title: 'Configuration', items: [{ label: 'Version', value: '1.29' }] }],
    };
    const sections = getVisibleCanvasSections(data, INSIGHT_PROFILES.kubernetes);
    expect(sections.indexOf('properties')).toBeLessThan(sections.indexOf('pools'));
    expect(sections.indexOf('pools')).toBeLessThan(sections.indexOf('recommendation'));
  });

  test('getVisibleCanvasSections includes instances for VMSS when instance metrics exist', () => {
    const data = {
      insights: null,
      advisor: [],
      trends: [],
      nodePools: [],
      metrics: [{ label: 'CPU', value: '10%' }],
      instances: [{ name: 'vmss000000', cpu: '10%', memory: '40%' }],
      canvasPropertyGroups: [{ title: 'Configuration', items: [{ label: 'VM size', value: 'Standard_D2s_v3' }] }],
    };
    const sections = getVisibleCanvasSections(data, INSIGHT_PROFILES.vmss);
    expect(sections).toContain('instances');
    expect(sections.indexOf('metrics')).toBeLessThan(sections.indexOf('instances'));
  });

  test('buildCanvasNodePools includes NAP pools from agent profiles', () => {
    const pools = buildCanvasNodePools({
      name: 'prod-aks',
      type: 'Microsoft.ContainerService/managedClusters',
      properties: {
        agentPoolProfiles: [
          { name: 'system', count: 2, vmSize: 'Standard_D2s_v3', mode: 'System' },
          { name: 'nap', count: 1, vmSize: 'Standard_D4s_v3', mode: 'Auto provisioning', _napPool: true },
        ],
      },
    });
    expect(pools).toHaveLength(2);
    expect(pools[1]).toMatchObject({ name: 'nap', mode: 'Auto provisioning', _napPool: true });
  });

  test('buildCanvasInstances maps VMSS instance metrics', () => {
    const instances = buildCanvasInstances({
      instances: [{
        name: 'vmss000000',
        instance_id: '0',
        power_state: 'PowerState/running',
        metrics_detail: [
          { fact_key: 'avg_cpu_pct', stats: { average: 18 } },
          { fact_key: 'avg_mem_pct', stats: { average: 42 } },
        ],
      }],
    });
    expect(instances).toHaveLength(1);
    expect(instances[0].name).toBe('vmss000000');
    expect(instances[0].cpuPct).toBe(18);
    expect(instances[0].memPct).toBe(42);
  });

  test('buildCanvasMetrics maps monitor rows to canvas grid items', () => {
    const metrics = buildCanvasMetrics({
      metrics: [{ fact_key: 'avg_cpu_pct', label: 'Average CPU', stats: { average: 22 }, unit: '%' }],
    });
    expect(metrics[0]).toMatchObject({ label: 'Average CPU', pct: 22 });
  });
});

describe('buildRationale', () => {
  test('prefers evidence summary over detail', () => {
    const text = buildRationale({
      detail: 'Long detail text.',
      evidence: { summary: 'Short summary from engine.' },
    });
    expect(text).toBe('Short summary from engine.');
  });

  test('truncates detail to first two sentences', () => {
    const text = buildRationale({
      detail: 'First sentence. Second sentence. Third sentence.',
    });
    expect(text).toBe('First sentence. Second sentence.');
  });
});

describe('buildEvidenceRows', () => {
  test('groups checks by utilization and cost', () => {
    const { groups } = buildEvidenceRows({
      evidence: {
        checks: [
          { signal: 'Average CPU', value: 12, threshold: '< 20%', passed: true },
          { signal: 'Month-to-date cost', value: 120, threshold: '—', passed: true, value_key: 'monthly_cost' },
        ],
        optimization_metrics: {
          performance: [
            { id: 'avg_cpu', label: 'Average CPU', formatted: '12%', value: 12, unit: '%', status: 'low' },
          ],
          cost: [
            { id: 'mtd_cost', label: 'Month-to-date cost', formatted: '$120.00', value: 120 },
          ],
        },
      },
    });

    const groupKeys = groups.map((g) => g.key);
    expect(groupKeys).toContain('utilization');
    expect(groupKeys).toContain('cost');
  });

    test('caps overflow rows', () => {
    const checks = Array.from({ length: 10 }, (_, i) => ({
      signal: `Signal ${i}`,
      value: i,
      threshold: '< 10',
      passed: true,
    }));
    const result = buildEvidenceRows({ evidence: { checks } });
    expect(result.totalCount).toBeLessThanOrEqual(8);
    expect(result.overflowCount).toBeGreaterThan(0);
  });

  test('excludes inventory properties from evidence rows', () => {
    const { groups } = buildEvidenceRows({
      evidence: {
        optimization_metrics: {
          performance: [
            { id: 'node_count', label: 'Node count', formatted: '2', value: 2, fact_key: 'node_count' },
            { id: 'cluster_cpu', label: 'Cluster CPU utilization', formatted: '8.2%', value: 8.2, fact_key: 'cluster_cpu_pct' },
            { id: 'k8s_version', label: 'Kubernetes version', formatted: '1.33.2', value: '1.33.2', fact_key: 'kubernetes_version' },
          ],
          cost: [],
        },
      },
    });
    const labels = groups.flatMap((g) => (g.rows || []).map((i) => i.label));
    expect(labels).toContain('Cluster CPU utilization');
    expect(labels).not.toContain('Node count');
    expect(labels).not.toContain('Kubernetes version');
  });
});

describe('pickPrimaryEvidenceMetric', () => {
  test('returns first percent optimization metric', () => {
    const metric = pickPrimaryEvidenceMetric({
      evidence: {
        optimization_metrics: {
          performance: [
            { id: 'avg_cpu', label: 'Average CPU', formatted: '22%', value: 22, unit: '%', status: 'low' },
          ],
        },
      },
    });
    expect(metric.pct).toBe(22);
    expect(metric.value).toBe('22%');
  });
});

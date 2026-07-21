import {
  normalizeEvidence,
  evidenceChecks,
  evidenceTechnicalChecks,
  evidenceSavingsMethodology,
  formatEvidenceLabel,
  extractResourceTechnicalDetails,
  evidenceOptimizationMetrics,
  optimizationDataQualityLabel,
  formatUtilizationTrend,
  filterPerformanceMetricsForContext,
  dedupeChecksAgainstMetrics,
  isPercentOptimizationMetric,
  parseOptimizationPercentValue,
  isInventoryPropertyEvidence,
  evidenceRequiredByPillar,
  formatEvidenceRow,
} from './evidenceUtils';

describe('evidenceUtils', () => {
  test('normalizeEvidence parses JSON strings', () => {
    expect(normalizeEvidence('{"summary":"ok"}')).toEqual({ summary: 'ok' });
    expect(normalizeEvidence('not-json')).toBeNull();
    expect(normalizeEvidence(null)).toBeNull();
  });

  test('evidenceChecks returns only arrays', () => {
    expect(evidenceChecks({ checks: [{ signal: 'a' }] })).toHaveLength(1);
    expect(evidenceChecks({ checks: 'bad' })).toEqual([]);
  });

  test('evidenceSavingsMethodology handles strings and objects', () => {
    expect(evidenceSavingsMethodology({ savings_methodology: 'Save full cost' }))
      .toEqual({ description: 'Save full cost' });
    expect(evidenceSavingsMethodology({
      savings_methodology: { description: 'Factor', formula: 'x * y', method: 'factor' },
    }).description).toBe('Factor');
  });

  test('formatEvidenceLabel coerces non-strings safely', () => {
    expect(formatEvidenceLabel('idle_no_listeners')).toBe('Idle — no HTTP listeners');
    expect(formatEvidenceLabel('low_throughput')).toBe('Low throughput');
    expect(formatEvidenceLabel({ code: 'idle' })).toBe('idle');
    expect(formatEvidenceLabel(null)).toBe('');
  });

  test('extractResourceTechnicalDetails prefers resource_details and excludes cost', () => {
    const rows = extractResourceTechnicalDetails({
      monthly_cost_usd: 120,
      savings_methodology: { method: 'full_monthly_cost' },
      resource_details: {
        http_listener_count: 0,
        sku: 'WAF_v2',
        monthly_cost_usd: 120,
      },
    });
    const labels = rows.map((r) => r.key);
    expect(labels).not.toContain('http_listener_count');
    expect(labels).not.toContain('sku');
    expect(labels).not.toContain('monthly_cost_usd');
  });

  test('extractResourceTechnicalDetails labels source disk ARM IDs', () => {
    const rows = extractResourceTechnicalDetails({
      resource_details: {
        source_disk_id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/disks/cso-54802-pgcore',
      },
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].label).toBe('Source disk');
    expect(rows[0].value).toContain('cso-54802-pgcore');
  });

  test('parseOptimizationPercentValue ignores SKU-like text values', () => {
    expect(isPercentOptimizationMetric({ id: 'sku', label: 'SKU', formatted: 'P2v3', unit: 'SKU' })).toBe(false);
    expect(parseOptimizationPercentValue('P2v3', 'P2v3')).toBeNull();
    expect(parseOptimizationPercentValue('Standard_D4s_v3', 'Standard_D4s_v3')).toBeNull();
    expect(isPercentOptimizationMetric({ id: 'avg_cpu', formatted: '3.0%', unit: '%' })).toBe(true);
    expect(parseOptimizationPercentValue('3.0%', 3)).toBe(3);
  });

  test('extractResourceTechnicalDetails excludes performance metrics owned by optimization_metrics', () => {
    const rows = extractResourceTechnicalDetails({
      vm_size: 'Standard_D2s_v3',
      avg_cpu_pct: 3.2,
      monthly_cost: 50,
      data_source: 'synced_inventory',
      missing_tags: ['Environment'],
    });
    expect(rows.some((r) => r.key === 'missing_tags')).toBe(false);
    expect(rows.some((r) => r.key === 'vm_size')).toBe(false);
    expect(rows.some((r) => r.key === 'avg_cpu_pct')).toBe(false);
    expect(rows.some((r) => r.key === 'monthly_cost')).toBe(false);
  });

  test('evidenceTechnicalChecks filters cost and performance signals', () => {
    const checks = evidenceTechnicalChecks({
      checks: [
        { signal: 'Month-to-date cost', value: '$50.00' },
        { signal: 'Peak CPU utilization', value: '3.0%', value_key: 'avg_cpu_pct' },
        { signal: 'HTTP listeners configured', value: 0, value_key: 'http_listener_count' },
        { signal: 'Missing required tag', value: 'Environment', value_key: 'missing_tags' },
      ],
    });
    expect(checks).toHaveLength(1);
    expect(checks[0].signal).toBe('Missing required tag');
  });

  test('evidenceOptimizationMetrics parses cost and performance blocks', () => {
    const block = evidenceOptimizationMetrics({
      optimization_metrics: {
        cost: [{ id: 'mtd_cost', label: 'Month-to-date cost', formatted: '$10.00' }],
        performance: [{ id: 'avg_cpu', label: 'Average CPU utilization', formatted: '3.0%', status: 'underutilized' }],
        data_quality: 'inventory_and_cost',
        component: 'compute/vm',
      },
    });
    expect(block.cost).toHaveLength(1);
    expect(block.performance).toHaveLength(1);
    expect(optimizationDataQualityLabel(block.dataQuality)).toBe('Synced inventory + cost data');
  });

  test('formatUtilizationTrend renders trend objects safely', () => {
    expect(formatUtilizationTrend('increasing')).toBe('Rising');
    expect(formatUtilizationTrend({
      slope: 'growing',
      growth_rate_per_week: 2.5,
      projected_4w: 52.1,
      current_value: 45.0,
      sample_count: 6,
      insufficient_history: false,
    })).toBe('Rising · +2.5%/wk · 45.0% → 52.1% (4w)');
    expect(formatUtilizationTrend({
      slope: 'unknown',
      insufficient_history: true,
      sample_count: 1,
    })).toBe('Insufficient data (1 wk)');
  });

  test('filterPerformanceMetricsForContext hides drawer duplicates', () => {
    const filtered = filterPerformanceMetricsForContext(
      [
        { id: 'disk_state', label: 'Disk state', formatted: 'Unattached' },
        { id: 'resource_state', label: 'Resource state', formatted: 'Unattached' },
        { id: 'sku', label: 'SKU', formatted: 'Premium_LRS' },
        { id: 'size_gb', label: 'Size', formatted: '128' },
        { id: 'provisioned_iops', label: 'Provisioned IOPS', formatted: '500' },
      ],
      {
        sku: 'Premium_LRS',
        resourceGroup: 'rg-1',
        state: 'Unattached',
        canonicalType: 'compute/disk',
        diskPropertiesShown: true,
      },
    );
    expect(filtered.map((m) => m.id)).toEqual([]);
  });

  test('dedupeChecksAgainstMetrics removes checks already shown as metrics', () => {
    const checks = dedupeChecksAgainstMetrics(
      [
        { signal: 'Average CPU utilization', value: '3.0%' },
        { signal: 'Missing required tag', value: 'Environment' },
      ],
      [{ id: 'avg_cpu', label: 'Average CPU utilization', formatted: '3.0%' }],
    );
    expect(checks).toHaveLength(1);
    expect(checks[0].signal).toBe('Missing required tag');
  });

  test('isInventoryPropertyEvidence flags node count and kubernetes version', () => {
    expect(isInventoryPropertyEvidence('Node count', 'node_count')).toBe(true);
    expect(isInventoryPropertyEvidence('Kubernetes version', 'kubernetes_version')).toBe(true);
    expect(isInventoryPropertyEvidence('Cluster CPU utilization', 'cluster_cpu_pct')).toBe(false);
    expect(isInventoryPropertyEvidence('Suggested SKU', 'suggested_sku')).toBe(true);
    expect(isInventoryPropertyEvidence('Disk state', 'disk_state')).toBe(true);
  });

  test('formatEvidenceRow normalizes structured insight rows for rendering', () => {
    const row = formatEvidenceRow({
      label: 'Pattern',
      value: 'Steady',
      detail: 'Usage stays flat — good fit for reserved capacity or fixed SKUs.',
      tone: 'neutral',
    });
    expect(row).toEqual({
      label: 'Pattern',
      value: 'Steady',
      detail: 'Usage stays flat — good fit for reserved capacity or fixed SKUs.',
      tone: 'neutral',
      major: false,
    });
    expect(formatEvidenceRow('Plain string')).toEqual({
      label: '',
      value: 'Plain string',
      detail: '',
      tone: '',
    });
  });

  test('evidenceRequiredByPillar groups contract rows by pillar', () => {
    const groups = evidenceRequiredByPillar({
      required_evidence: [
        { signal: 'cpu_utilization_pct', label: 'Average CPU utilization', pillar: 'performance', aggregation: 'avg', period: '7d' },
        { signal: 'monthly_cost_usd', label: 'Month-to-date cost', pillar: 'cost', aggregation: 'sum', period: 'MTD' },
      ],
      optimization_metrics: {
        performance: [{ id: 'avg_cpu', fact_key: 'cpu_utilization_pct', label: 'Average CPU utilization', formatted: '3.0%' }],
        cost: [{ id: 'mtd_cost', label: 'Month-to-date cost', formatted: '$50.00' }],
      },
    });
    expect(groups.map((g) => g.pillar)).toEqual(['performance', 'cost']);
    expect(groups[0].items[0].label).toBe('Average CPU utilization');
  });

  test('evidenceOptimizationMetrics excludes inventory property metrics', () => {
    const block = evidenceOptimizationMetrics({
      optimization_metrics: {
        performance: [
          { id: 'node_count', fact_key: 'node_count', label: 'Node count', formatted: '4' },
          { id: 'cluster_cpu', fact_key: 'cluster_cpu_pct', label: 'Cluster CPU utilization', formatted: '8.2%' },
        ],
        cost: [],
      },
    });
    const labels = (block?.performance || []).map((m) => m.label);
    expect(labels).not.toContain('Node count');
    expect(labels).toContain('Cluster CPU utilization');
  });

  test('extractResourceTechnicalDetails excludes engine metadata keys', () => {
    const rows = extractResourceTechnicalDetails({
      engine: 'assessment_json',
      rule_source: 'assessment_json',
      sub_engine: 'database/cosmosdb',
      recommendation_action: 'migrate_region',
      pillar: 'governance',
      offer_type: 'Standard',
      region_count: 2,
      normalized_ru_pct: 42.5,
    });
    const keys = rows.map((row) => row.key);
    expect(keys).not.toContain('engine');
    expect(keys).not.toContain('offer_type');
    expect(keys).not.toContain('sub_engine');
    expect(keys).toContain('normalized_ru_pct');
  });
});

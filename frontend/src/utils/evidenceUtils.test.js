import {
  normalizeEvidence,
  evidenceChecks,
  evidenceTechnicalChecks,
  evidenceSavingsMethodology,
  formatEvidenceLabel,
  extractResourceTechnicalDetails,
  evidenceOptimizationMetrics,
  optimizationDataQualityLabel,
  filterPerformanceMetricsForContext,
  dedupeChecksAgainstMetrics,
  extractAiInsight,
  formatAiRiskLabel,
  findingHasAiInsight,
  isPercentOptimizationMetric,
  parseOptimizationPercentValue,
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
    expect(rows.some((r) => r.key === 'missing_tags')).toBe(true);
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

  test('extractAiInsight parses ai_insight block', () => {
    const insight = extractAiInsight({
      ai_insight: {
        executive_summary: 'Disk idle 90 days.',
        recommendation: 'Delete after backup check.',
        rule_recommendation: 'Delete disk.',
        implementation_steps: ['Validate backups', 'Delete disk'],
        risk_level: 'medium',
        data_gaps: ['No I/O metrics'],
      },
    });
    expect(insight.executiveSummary).toBe('Disk idle 90 days.');
    expect(insight.implementationSteps).toHaveLength(2);
    expect(formatAiRiskLabel('medium')).toBe('Medium risk');
  });

  test('findingHasAiInsight detects api flag and evidence block', () => {
    expect(findingHasAiInsight({ ai_enriched: true })).toBe(true);
    expect(findingHasAiInsight({ evidence: { ai_insight: { recommendation: 'x' } } })).toBe(true);
    expect(findingHasAiInsight({ evidence: {} })).toBe(false);
  });
});

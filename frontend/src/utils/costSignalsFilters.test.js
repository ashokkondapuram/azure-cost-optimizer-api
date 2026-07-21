import {
  filterCostDrivers,
  filterCostDrivingMetrics,
  filterMetricsBundleForCostSignals,
  isGovernanceCostSignal,
  countCostDrivers,
  countCostSignalTriggers,
} from './costSignalsFilters';

describe('costSignalsFilters', () => {
  test('isGovernanceCostSignal detects region approval labels and keys', () => {
    expect(isGovernanceCostSignal({ label: 'Region approval', fact_key: 'region_classification' })).toBe(true);
    expect(isGovernanceCostSignal({ label: 'Approve region', fact_key: 'custom' })).toBe(true);
    expect(isGovernanceCostSignal({ fact_key: 'regionApproved' })).toBe(true);
    expect(isGovernanceCostSignal({ kind: 'region', label: 'Recommended region' })).toBe(true);
    expect(isGovernanceCostSignal({ rules: ['best_unapproved_region'] })).toBe(true);
    expect(isGovernanceCostSignal({ id: 'region-classification' })).toBe(true);
  });

  test('isGovernanceCostSignal keeps cost and utilization metrics', () => {
    expect(isGovernanceCostSignal({ fact_key: 'avg_cpu_pct', label: 'Average CPU utilization' })).toBe(false);
    expect(isGovernanceCostSignal({ fact_key: 'monthly_cost_usd', label: 'Month-to-date cost' })).toBe(false);
    expect(isGovernanceCostSignal({ fact_key: 'region_count', label: 'Region count' })).toBe(false);
  });

  test('filterMetricsBundleForCostSignals removes governance rows only', () => {
    const bundle = {
      metrics: [
        { fact_key: 'avg_cpu_pct', label: 'Average CPU', trigger: { threshold: '< 5%' } },
        { fact_key: 'regionApproved', label: 'Region approval', trigger: { threshold: 'approved' } },
      ],
      derived: [],
      cost_driver_mapping: {
        cost_drivers: [
          { kind: 'metric', fact_key: 'avg_cpu_pct', label: 'Average CPU' },
          { kind: 'region', fact_key: 'region_classification', label: 'Region approval' },
        ],
      },
    };

    const filtered = filterMetricsBundleForCostSignals(bundle);
    expect(filtered.metrics).toHaveLength(1);
    expect(filtered.metrics[0].fact_key).toBe('avg_cpu_pct');
    expect(filtered.cost_driver_mapping.cost_drivers).toHaveLength(1);
    expect(filterCostDrivingMetrics(bundle.metrics)).toHaveLength(1);
    expect(filterCostDrivers(bundle.cost_driver_mapping.cost_drivers)).toHaveLength(1);
    expect(countCostDrivers(bundle)).toBe(1);
    expect(countCostSignalTriggers(bundle)).toBe(1);
  });

  test('countCostDrivers and countCostSignalTriggers return 0 when bundle is missing', () => {
    expect(countCostDrivers(null)).toBe(0);
    expect(countCostDrivers(undefined)).toBe(0);
    expect(countCostSignalTriggers(null)).toBe(0);
    expect(countCostSignalTriggers(undefined)).toBe(0);
  });
});

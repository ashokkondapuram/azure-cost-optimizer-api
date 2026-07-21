import {
  DEFAULT_METRIC_TIMESPAN,
  METRIC_TIMESPAN_OPTIONS,
  coerceMetricTimespan,
  isValidMetricTimespan,
  metricTimespanLabel,
} from './metricsTimespanUtils';

describe('metricsTimespanUtils', () => {
  it('labels known timespans', () => {
    expect(metricTimespanLabel('P7D')).toBe('Last 7 days');
    expect(metricTimespanLabel('P30D')).toBe('Last 30 days');
    expect(metricTimespanLabel('unknown')).toBe('unknown');
  });

  it('validates supported timespans', () => {
    expect(isValidMetricTimespan('P7D')).toBe(true);
    expect(isValidMetricTimespan('P1Y')).toBe(false);
    expect(DEFAULT_METRIC_TIMESPAN).toBe('P7D');
    expect(METRIC_TIMESPAN_OPTIONS.length).toBeGreaterThan(2);
  });

  it('coerces object-shaped persisted timespans', () => {
    expect(coerceMetricTimespan({ value: 'P14D' })).toBe('P14D');
    expect(coerceMetricTimespan('P30D')).toBe('P30D');
    expect(coerceMetricTimespan({ foo: 'bar' })).toBe(DEFAULT_METRIC_TIMESPAN);
    expect(coerceMetricTimespan('p7d')).toBe('P7D');
    expect(coerceMetricTimespan('[object Object]')).toBe(DEFAULT_METRIC_TIMESPAN);
    expect(coerceMetricTimespan('{"value":"P14D","label":"Last 14 days"}')).toBe('P14D');
  });
});

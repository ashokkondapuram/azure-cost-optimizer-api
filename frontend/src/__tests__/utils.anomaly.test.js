function toAnomalyRow(change) {
  const spike    = Number(change.current_cost  || change.cost      || 0);
  const baseline = Number(change.previous_cost || change.base_cost || 0);
  const pct      = baseline > 0 ? Math.round(((spike - baseline) / baseline) * 100) : 0;
  const severity = pct >= 50 ? 'high' : pct >= 20 ? 'medium' : 'low';
  return {
    id:       change.id || change.resource_id || (change.service + '-' + change.date),
    date:     change.date || change.period || '—',
    service:  change.service || change.service_name || change.resource_type || 'Unknown',
    spike, baseline, pct, severity,
    status:   change.status || 'open',
    reason:   change.reason || change.description || 'Cost increase detected',
  };
}

describe('toAnomalyRow', () => {
  test('current_cost/previous_cost fields → 100% spike (high)', () => {
    const r = toAnomalyRow({ id:'1', current_cost:200, previous_cost:100, service:'VMs', date:'2026-07-01' });
    expect(r.pct).toBe(100); expect(r.severity).toBe('high');
  });
  test('cost/base_cost alias → medium severity', () => {
    const r = toAnomalyRow({ id:'2', cost:125, base_cost:100, service:'Storage' });
    expect(r.pct).toBe(25); expect(r.severity).toBe('medium');
  });
  test('low severity when pct < 20', () => {
    expect(toAnomalyRow({ id:'3', current_cost:110, previous_cost:100, service:'SQL' }).severity).toBe('low');
  });
  test('zero pct when baseline is 0', () => {
    expect(toAnomalyRow({ id:'4', current_cost:50, previous_cost:0, service:'AKS' }).pct).toBe(0);
  });
  test('id falls back to service-date composite', () => {
    expect(toAnomalyRow({ service:'Redis', date:'2026-07-04', cost:10, base_cost:8 }).id).toBe('Redis-2026-07-04');
  });
  test('service fallback: service_name', () => {
    expect(toAnomalyRow({ service_name:'Cosmos DB', cost:1 }).service).toBe('Cosmos DB');
  });
  test('service fallback: resource_type', () => {
    expect(toAnomalyRow({ resource_type:'Microsoft.Compute/virtualMachines', cost:1 }).service)
      .toBe('Microsoft.Compute/virtualMachines');
  });
  test('service fallback: Unknown', () => {
    expect(toAnomalyRow({ cost:1 }).service).toBe('Unknown');
  });
  test('preserves existing status', () => {
    expect(toAnomalyRow({ id:'5', status:'resolved', cost:200, base_cost:100 }).status).toBe('resolved');
  });
  test('defaults to open status', () => {
    expect(toAnomalyRow({ id:'6', cost:10 }).status).toBe('open');
  });
});

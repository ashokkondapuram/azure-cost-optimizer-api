// ============================================================
// utils.anomaly — rigorous tests
// Mirrors CostAnomalyDetector.jsx: toAnomalyRow
// ============================================================

function toAnomalyRow(change) {
  const spike    = Number(change.current_cost   || change.cost       || 0);
  const baseline = Number(change.previous_cost  || change.base_cost  || 0);
  const pct      = baseline > 0 ? Math.round(((spike - baseline) / baseline) * 100) : 0;
  const severity = pct >= 50 ? 'high' : pct >= 20 ? 'medium' : 'low';
  return {
    id:       change.id || change.resource_id || `${change.service}-${change.date}`,
    date:     change.date || change.period || '—',
    service:  change.service || change.service_name || change.resource_type || 'Unknown',
    spike,
    baseline,
    pct,
    severity,
    status:   change.status || 'open',
    reason:   change.reason || change.description || 'Cost increase detected',
  };
}

// ── cost field aliases ────────────────────────────────────────
describe('toAnomalyRow — cost field resolution', () => {
  test('current_cost / previous_cost (primary)', () => {
    const r = toAnomalyRow({ id:'1', current_cost:200, previous_cost:100 });
    expect(r.spike).toBe(200); expect(r.baseline).toBe(100);
  });
  test('cost / base_cost (aliases)', () => {
    const r = toAnomalyRow({ id:'2', cost:125, base_cost:100 });
    expect(r.spike).toBe(125); expect(r.baseline).toBe(100);
  });
  test('current_cost wins over cost alias', () => {
    const r = toAnomalyRow({ current_cost:300, cost:10, previous_cost:100, base_cost:50 });
    expect(r.spike).toBe(300); expect(r.baseline).toBe(100);
  });
  test('string values are coerced to numbers', () => {
    const r = toAnomalyRow({ current_cost:'200', previous_cost:'100' });
    expect(r.spike).toBe(200); expect(r.baseline).toBe(100);
  });
  test('missing cost fields default to 0', () => {
    const r = toAnomalyRow({});
    expect(r.spike).toBe(0); expect(r.baseline).toBe(0);
  });
});

// ── pct calculation ───────────────────────────────────────────
describe('toAnomalyRow — pct calculation', () => {
  test('100% spike', () => {
    expect(toAnomalyRow({ current_cost:200, previous_cost:100 }).pct).toBe(100);
  });
  test('50% spike', () => {
    expect(toAnomalyRow({ current_cost:150, previous_cost:100 }).pct).toBe(50);
  });
  test('25% spike', () => {
    expect(toAnomalyRow({ current_cost:125, previous_cost:100 }).pct).toBe(25);
  });
  test('10% spike', () => {
    expect(toAnomalyRow({ current_cost:110, previous_cost:100 }).pct).toBe(10);
  });
  test('0% when spike === baseline', () => {
    expect(toAnomalyRow({ current_cost:100, previous_cost:100 }).pct).toBe(0);
  });
  test('negative pct when cost decreases', () => {
    expect(toAnomalyRow({ current_cost:80, previous_cost:100 }).pct).toBe(-20);
  });
  test('zero pct when baseline is 0 (avoid division by zero)', () => {
    expect(toAnomalyRow({ current_cost:50, previous_cost:0 }).pct).toBe(0);
  });
  test('pct is rounded (not float)', () => {
    // 110/300 ≈ 36.67% → rounds to 37
    const r = toAnomalyRow({ current_cost:410, previous_cost:300 });
    expect(Number.isInteger(r.pct)).toBe(true);
    expect(r.pct).toBe(37);
  });
});

// ── severity thresholds ───────────────────────────────────────
describe('toAnomalyRow — severity thresholds', () => {
  test.each([
    [200, 100, 'high'],    // 100% → high
    [150, 100, 'high'],    // 50%  → high (boundary)
    [149, 100, 'medium'],  // 49%  → medium (just below boundary)
    [120, 100, 'medium'],  // 20%  → medium (boundary)
    [119, 100, 'low'],     // 19%  → low
    [100, 100, 'low'],     // 0%   → low
    [50,  100, 'low'],     // -50% → low (decrease)
  ])('spike=%d baseline=%d → severity=%s', (spike, baseline, expected) => {
    expect(toAnomalyRow({ current_cost: spike, previous_cost: baseline }).severity).toBe(expected);
  });
});

// ── id resolution ─────────────────────────────────────────────
describe('toAnomalyRow — id resolution', () => {
  test('change.id used first', () => {
    expect(toAnomalyRow({ id:'direct', resource_id:'rid', service:'s', date:'d' }).id).toBe('direct');
  });
  test('resource_id used when id absent', () => {
    expect(toAnomalyRow({ resource_id:'rid', service:'s', date:'d' }).id).toBe('rid');
  });
  test('service-date composite when both absent', () => {
    expect(toAnomalyRow({ service:'Redis', date:'2026-07-04' }).id).toBe('Redis-2026-07-04');
  });
  test('id=0 (falsy) falls through to resource_id', () => {
    expect(toAnomalyRow({ id: 0, resource_id:'rid2' }).id).toBe('rid2');
  });
});

// ── service resolution ────────────────────────────────────────
describe('toAnomalyRow — service resolution', () => {
  test('service field wins', () => {
    expect(toAnomalyRow({ service:'VMs', service_name:'Other' }).service).toBe('VMs');
  });
  test('service_name fallback', () => {
    expect(toAnomalyRow({ service_name:'Cosmos DB' }).service).toBe('Cosmos DB');
  });
  test('resource_type fallback', () => {
    expect(toAnomalyRow({ resource_type:'Microsoft.Compute/disks' }).service).toBe('Microsoft.Compute/disks');
  });
  test('"Unknown" when all absent', () => {
    expect(toAnomalyRow({}).service).toBe('Unknown');
  });
});

// ── status and reason ─────────────────────────────────────────
describe('toAnomalyRow — status / reason', () => {
  test('preserves existing status', () => {
    expect(toAnomalyRow({ status: 'resolved' }).status).toBe('resolved');
  });
  test('defaults status to "open"', () => {
    expect(toAnomalyRow({}).status).toBe('open');
  });
  test('reason field used when present', () => {
    expect(toAnomalyRow({ reason: 'Spike due to indexing job' }).reason).toBe('Spike due to indexing job');
  });
  test('description alias used when reason absent', () => {
    expect(toAnomalyRow({ description: 'Scheduled maintenance' }).reason).toBe('Scheduled maintenance');
  });
  test('default reason when both absent', () => {
    expect(toAnomalyRow({}).reason).toBe('Cost increase detected');
  });
});

// ── date resolution ───────────────────────────────────────────
describe('toAnomalyRow — date resolution', () => {
  test('date field used first', () => {
    expect(toAnomalyRow({ date:'2026-07-01', period:'2026-06-01' }).date).toBe('2026-07-01');
  });
  test('period alias used when date absent', () => {
    expect(toAnomalyRow({ period:'2026-06-01' }).date).toBe('2026-06-01');
  });
  test('em-dash when both absent', () => {
    expect(toAnomalyRow({}).date).toBe('—');
  });
});

// ── shape invariants ──────────────────────────────────────────
describe('toAnomalyRow — shape invariants', () => {
  const REQUIRED = ['id','date','service','spike','baseline','pct','severity','status','reason'];
  test('always returns all required keys', () => {
    REQUIRED.forEach(k => expect(toAnomalyRow({})).toHaveProperty(k));
  });
  test('severity is always one of high|medium|low', () => {
    [{ current_cost:500, previous_cost:100 }, {}, { current_cost:80, previous_cost:100 }].forEach(c => {
      expect(['high','medium','low']).toContain(toAnomalyRow(c).severity);
    });
  });
});

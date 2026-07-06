// ============================================================
// utils.timeline — rigorous tests
// Mirrors OptimizationTimeline.jsx: actionToEvent + findingToEvent
// ============================================================

function actionToEvent(a) {
  const status = (a.status || '').toLowerCase();
  let type = 'other';
  if (status === 'executed' || status === 'completed')   type = 'action_executed';
  else if (status === 'rejected' || status === 'failed') type = 'action_rejected';
  else if (status === 'approved')                        type = 'action_approved';
  else if (status === 'pending')                         type = 'action_pending';
  return {
    id:       'action-' + (a.id || a.action_id),
    ts:       a.updated_at || a.executed_at || a.created_at || '—',
    actor:    a.assigned_to || a.executed_by || 'system',
    type,
    resource: a.resource_name || a.resource_id || '—',
    detail:   a.title || a.description || a.action_type || '—',
    outcome:  status === 'executed' || status === 'completed' ? 'success'
              : status === 'rejected' || status === 'failed'  ? 'warning'
              : 'info',
    savings:  Number(a.estimated_savings || 0) || null,
  };
}

function findingToEvent(f) {
  const status = (f.status || '').toLowerCase();
  let type = 'finding_open';
  if (status === 'resolved')                               type = 'finding_resolved';
  else if (status === 'ignored' || status === 'dismissed') type = 'finding_ignored';
  return {
    id:       'finding-' + (f.id || f.finding_id),
    ts:       f.updated_at || f.created_at || '—',
    actor:    f.updated_by || 'system',
    type,
    resource: f.resource_name || f.resource_id || '—',
    detail:   f.title || f.description || '—',
    outcome:  status === 'resolved' ? 'success'
              : (status === 'ignored' || status === 'dismissed') ? 'warning'
              : 'info',
    savings:  Number(f.estimated_monthly_savings || f.savings || 0) || null,
  };
}

// ── actionToEvent: type + outcome matrix ─────────────────────
describe('actionToEvent — type/outcome', () => {
  test.each([
    ['executed',   'action_executed', 'success'],
    ['EXECUTED',   'action_executed', 'success'],  // case-insensitive
    ['completed',  'action_executed', 'success'],
    ['COMPLETED',  'action_executed', 'success'],
    ['rejected',   'action_rejected', 'warning'],
    ['failed',     'action_rejected', 'warning'],
    ['FAILED',     'action_rejected', 'warning'],
    ['approved',   'action_approved', 'info'],
    ['APPROVED',   'action_approved', 'info'],
    ['pending',    'action_pending',  'info'],
    ['PENDING',    'action_pending',  'info'],
    ['unknown',    'other',           'info'],
    ['',           'other',           'info'],
    ['in_progress','other',           'info'],
  ])('status="%s" → type=%s outcome=%s', (status, expectedType, expectedOutcome) => {
    const e = actionToEvent({ id: '1', status });
    expect(e.type).toBe(expectedType);
    expect(e.outcome).toBe(expectedOutcome);
  });
});

// ── actionToEvent: id ────────────────────────────────────────
describe('actionToEvent — id', () => {
  test('id field used when present', () => {
    expect(actionToEvent({ id: '42' }).id).toBe('action-42');
  });
  test('action_id used as fallback when id absent', () => {
    expect(actionToEvent({ action_id: '99' }).id).toBe('action-99');
  });
  test('numeric id coerced to string via template literal', () => {
    expect(actionToEvent({ id: 7 }).id).toBe('action-7');
  });
  test('id=0 is falsy — falls back to action_id', () => {
    expect(actionToEvent({ id: 0, action_id: 'fallback' }).id).toBe('action-fallback');
  });
});

// ── actionToEvent: timestamp priority ────────────────────────
describe('actionToEvent — timestamp priority', () => {
  test('updated_at wins over executed_at and created_at', () => {
    expect(actionToEvent({ id:'1', updated_at:'2026-07-01', executed_at:'2026-06-01', created_at:'2026-05-01' }).ts)
      .toBe('2026-07-01');
  });
  test('executed_at used when updated_at absent', () => {
    expect(actionToEvent({ id:'1', executed_at:'2026-06-01', created_at:'2026-05-01' }).ts).toBe('2026-06-01');
  });
  test('created_at used when both others absent', () => {
    expect(actionToEvent({ id:'1', created_at:'2026-05-01' }).ts).toBe('2026-05-01');
  });
  test('em-dash when all timestamps absent', () => {
    expect(actionToEvent({ id:'1' }).ts).toBe('—');
  });
});

// ── actionToEvent: actor priority ────────────────────────────
describe('actionToEvent — actor priority', () => {
  test('assigned_to takes precedence over executed_by', () => {
    expect(actionToEvent({ id:'1', assigned_to:'alice', executed_by:'bob' }).actor).toBe('alice');
  });
  test('executed_by used when assigned_to absent', () => {
    expect(actionToEvent({ id:'1', executed_by:'bob' }).actor).toBe('bob');
  });
  test('defaults to "system"', () => {
    expect(actionToEvent({ id:'1' }).actor).toBe('system');
  });
  test('empty string assigned_to falls through to executed_by', () => {
    expect(actionToEvent({ id:'1', assigned_to:'', executed_by:'carol' }).actor).toBe('carol');
  });
});

// ── actionToEvent: detail priority ───────────────────────────
describe('actionToEvent — detail priority', () => {
  test('title wins over description and action_type', () => {
    expect(actionToEvent({ id:'1', title:'T', description:'D', action_type:'AT' }).detail).toBe('T');
  });
  test('description used when title absent', () => {
    expect(actionToEvent({ id:'1', description:'D', action_type:'AT' }).detail).toBe('D');
  });
  test('action_type used as last resort', () => {
    expect(actionToEvent({ id:'1', action_type:'AT' }).detail).toBe('AT');
  });
  test('em-dash when all detail fields absent', () => {
    expect(actionToEvent({ id:'1' }).detail).toBe('—');
  });
});

// ── actionToEvent: savings ────────────────────────────────────
describe('actionToEvent — savings', () => {
  test('positive savings returned as number', () => {
    expect(actionToEvent({ id:'1', estimated_savings: 250 }).savings).toBe(250);
  });
  test('string savings coerced to number', () => {
    expect(actionToEvent({ id:'1', estimated_savings: '175.5' }).savings).toBe(175.5);
  });
  test('zero savings → null', () => {
    expect(actionToEvent({ id:'1', estimated_savings: 0 }).savings).toBeNull();
  });
  test('absent savings → null', () => {
    expect(actionToEvent({ id:'1' }).savings).toBeNull();
  });
  test('negative savings returned (cost increase)', () => {
    expect(actionToEvent({ id:'1', estimated_savings: -50 }).savings).toBe(-50);
  });
});

// ── findingToEvent: type + outcome matrix ─────────────────────
describe('findingToEvent — type/outcome', () => {
  test.each([
    ['resolved',   'finding_resolved', 'success'],
    ['RESOLVED',   'finding_resolved', 'success'],
    ['ignored',    'finding_ignored',  'warning'],
    ['IGNORED',    'finding_ignored',  'warning'],
    ['dismissed',  'finding_ignored',  'warning'],
    ['DISMISSED',  'finding_ignored',  'warning'],
    ['open',       'finding_open',     'info'],
    ['OPEN',       'finding_open',     'info'],
    ['new',        'finding_open',     'info'],
    ['',           'finding_open',     'info'],
  ])('status="%s" → type=%s outcome=%s', (status, expectedType, expectedOutcome) => {
    const e = findingToEvent({ id: '1', status });
    expect(e.type).toBe(expectedType);
    expect(e.outcome).toBe(expectedOutcome);
  });
});

// ── findingToEvent: id ────────────────────────────────────────
describe('findingToEvent — id', () => {
  test('id field used when present', () => {
    expect(findingToEvent({ id: 'abc' }).id).toBe('finding-abc');
  });
  test('finding_id used as fallback', () => {
    expect(findingToEvent({ finding_id: 'xyz' }).id).toBe('finding-xyz');
  });
  test('id=0 falls through to finding_id', () => {
    expect(findingToEvent({ id: 0, finding_id: 'fb' }).id).toBe('finding-fb');
  });
});

// ── findingToEvent: timestamp priority ───────────────────────
describe('findingToEvent — timestamp priority', () => {
  test('updated_at wins over created_at', () => {
    expect(findingToEvent({ id:'1', updated_at:'2026-07-02', created_at:'2026-05-01' }).ts).toBe('2026-07-02');
  });
  test('created_at used when updated_at absent', () => {
    expect(findingToEvent({ id:'1', created_at:'2026-05-01' }).ts).toBe('2026-05-01');
  });
  test('em-dash default', () => {
    expect(findingToEvent({ id:'1' }).ts).toBe('—');
  });
});

// ── findingToEvent: savings ───────────────────────────────────
describe('findingToEvent — savings', () => {
  test('estimated_monthly_savings wins over savings', () => {
    expect(findingToEvent({ id:'1', estimated_monthly_savings: 300, savings: 10 }).savings).toBe(300);
  });
  test('savings alias used when primary absent', () => {
    expect(findingToEvent({ id:'1', savings: 75 }).savings).toBe(75);
  });
  test('zero → null', () => {
    expect(findingToEvent({ id:'1', savings: 0 }).savings).toBeNull();
  });
  test('absent → null', () => {
    expect(findingToEvent({ id:'1' }).savings).toBeNull();
  });
  test('string savings coerced', () => {
    expect(findingToEvent({ id:'1', estimated_monthly_savings: '120' }).savings).toBe(120);
  });
});

// ── invariants ────────────────────────────────────────────────
describe('event shape invariants', () => {
  const ACTION_KEYS   = ['id','ts','actor','type','resource','detail','outcome','savings'];
  const FINDING_KEYS  = ['id','ts','actor','type','resource','detail','outcome','savings'];

  test('actionToEvent always returns all required keys', () => {
    const e = actionToEvent({ id:'x', status:'executed' });
    ACTION_KEYS.forEach(k => expect(e).toHaveProperty(k));
  });

  test('findingToEvent always returns all required keys', () => {
    const e = findingToEvent({ id:'x', status:'open' });
    FINDING_KEYS.forEach(k => expect(e).toHaveProperty(k));
  });

  test('actionToEvent outcome is always one of success|warning|info', () => {
    ['executed','completed','rejected','failed','approved','pending','unknown',''].forEach(status => {
      expect(['success','warning','info']).toContain(actionToEvent({ id:'1', status }).outcome);
    });
  });

  test('findingToEvent outcome is always one of success|warning|info', () => {
    ['resolved','ignored','dismissed','open','new',''].forEach(status => {
      expect(['success','warning','info']).toContain(findingToEvent({ id:'1', status }).outcome);
    });
  });
});

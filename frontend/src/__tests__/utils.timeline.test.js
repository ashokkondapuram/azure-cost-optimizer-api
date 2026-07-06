function actionToEvent(a) {
  const status = (a.status || '').toLowerCase();
  let type = 'other';
  if (status === 'executed' || status === 'completed')   type = 'action_executed';
  else if (status === 'rejected' || status === 'failed') type = 'action_rejected';
  else if (status === 'approved')                        type = 'action_approved';
  else if (status === 'pending')                         type = 'action_pending';
  return {
    id:      'action-' + (a.id || a.action_id),
    ts:      a.updated_at || a.executed_at || a.created_at || '—',
    actor:   a.assigned_to || a.executed_by || 'system',
    type,
    resource:a.resource_name || a.resource_id || '—',
    detail:  a.title || a.description || a.action_type || '—',
    outcome: status === 'executed' || status === 'completed' ? 'success'
             : status === 'rejected' || status === 'failed'  ? 'warning' : 'info',
    savings: Number(a.estimated_savings || 0) || null,
  };
}

function findingToEvent(f) {
  const status = (f.status || '').toLowerCase();
  let type = 'finding_open';
  if (status === 'resolved')                               type = 'finding_resolved';
  else if (status === 'ignored' || status === 'dismissed') type = 'finding_ignored';
  return {
    id:      'finding-' + (f.id || f.finding_id),
    ts:      f.updated_at || f.created_at || '—',
    actor:   f.updated_by || 'system',
    type,
    resource:f.resource_name || f.resource_id || '—',
    detail:  f.title || f.description || '—',
    outcome: status === 'resolved' ? 'success'
             : (status === 'ignored' || status === 'dismissed') ? 'warning'
             : 'info',
    savings: Number(f.estimated_monthly_savings || f.savings || 0) || null,
  };
}

describe('actionToEvent', () => {
  test.each([
    ['executed',  'action_executed',  'success'],
    ['completed', 'action_executed',  'success'],
    ['rejected',  'action_rejected',  'warning'],
    ['failed',    'action_rejected',  'warning'],
    ['approved',  'action_approved',  'info'],
    ['pending',   'action_pending',   'info'],
    ['unknown',   'other',            'info'],
    ['',          'other',            'info'],
  ])('status=%s → type=%s outcome=%s', (status, expectedType, expectedOutcome) => {
    const e = actionToEvent({ id:'1', status, resource_name:'vm-1', title:'Resize VM' });
    expect(e.type).toBe(expectedType);
    expect(e.outcome).toBe(expectedOutcome);
  });
  test('id prefixed with action-', () => { expect(actionToEvent({ id:'42', status:'executed' }).id).toBe('action-42'); });
  test('uses action_id fallback', () => { expect(actionToEvent({ action_id:'99', status:'pending' }).id).toBe('action-99'); });
  test('actor: assigned_to wins', () => { expect(actionToEvent({ id:'1', assigned_to:'alice' }).actor).toBe('alice'); });
  test('actor: executed_by fallback', () => { expect(actionToEvent({ id:'1', executed_by:'bob' }).actor).toBe('bob'); });
  test('actor: system default', () => { expect(actionToEvent({ id:'1' }).actor).toBe('system'); });
  test('savings null when 0', () => { expect(actionToEvent({ id:'1', estimated_savings:0 }).savings).toBeNull(); });
  test('savings returned when positive', () => { expect(actionToEvent({ id:'1', estimated_savings:150 }).savings).toBe(150); });
});

describe('findingToEvent', () => {
  test.each([
    ['resolved',   'finding_resolved', 'success'],
    ['ignored',    'finding_ignored',  'warning'],
    ['dismissed',  'finding_ignored',  'warning'],
    ['open',       'finding_open',     'info'],
    ['',           'finding_open',     'info'],
  ])('status=%s → type=%s outcome=%s', (status, expectedType, expectedOutcome) => {
    const e = findingToEvent({ id:'1', status });
    expect(e.type).toBe(expectedType);
    expect(e.outcome).toBe(expectedOutcome);
  });
  test('id prefixed with finding-', () => { expect(findingToEvent({ id:'abc' }).id).toBe('finding-abc'); });
  test('finding_id fallback', () => { expect(findingToEvent({ finding_id:'xyz' }).id).toBe('finding-xyz'); });
  test('savings from estimated_monthly_savings', () => { expect(findingToEvent({ id:'1', estimated_monthly_savings:200 }).savings).toBe(200); });
  test('savings from savings alias', () => { expect(findingToEvent({ id:'1', savings:75 }).savings).toBe(75); });
  test('savings null when 0', () => { expect(findingToEvent({ id:'1', savings:0 }).savings).toBeNull(); });
});

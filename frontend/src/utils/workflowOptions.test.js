import { quickWorkflowOptions } from './workflowOptions';

describe('quickWorkflowOptions', () => {
  it('returns approve, reject, and defer for admins on proposed actions', () => {
    const options = quickWorkflowOptions({ isAdmin: true, currentStatus: 'proposed' });
    expect(options.map((option) => option.value)).toEqual(['approved', 'deferred', 'rejected']);
  });

  it('returns defer only for non-admins on proposed actions', () => {
    const options = quickWorkflowOptions({ isAdmin: false, currentStatus: 'proposed' });
    expect(options.map((option) => option.value)).toEqual(['deferred']);
  });

  it('returns no quick actions for non-proposed statuses', () => {
    expect(quickWorkflowOptions({ isAdmin: true, currentStatus: 'approved' })).toEqual([]);
  });
});

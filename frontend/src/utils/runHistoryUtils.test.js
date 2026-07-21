import { buildRunHistoryItems, jobStatusLabel } from './runHistoryUtils';

describe('runHistoryUtils', () => {
  it('merges jobs and runs with job status as source of truth', () => {
    const runs = [{
      id: 'run-1',
      analyzed_at: '2026-01-01T10:00:00Z',
      engine_version: 'extended',
      profile: 'default',
      total_findings: 5,
      total_savings_usd: 100,
      critical: 1,
      high: 2,
    }];
    const jobs = [
      {
        id: 'job-1',
        run_id: 'run-1',
        status: 'completed',
        status_label: 'Completed',
        engine_version: 'extended',
        profile: 'default',
        scope_label: 'Full analysis',
        components: [{ component: 'Full analysis', status: 'completed', findings: 5, savings_usd: 100 }],
        completed_at: '2026-01-01T10:05:00Z',
      },
      {
        id: 'job-2',
        status: 'failed',
        status_label: 'Failed',
        engine_version: 'extended',
        profile: 'default',
        scope_label: 'Compute',
        components: [{ component: 'Compute', status: 'failed' }],
        error_message: 'Cancelled by user.',
        completed_at: '2026-01-02T09:00:00Z',
      },
    ];

    const items = buildRunHistoryItems(runs, jobs);
    expect(items).toHaveLength(2);
    expect(items[0].key).toBe('job-2');
    expect(items[0].status).toBe('failed');
    expect(items[0].runId).toBeNull();
    expect(items[1].key).toBe('run-1');
    expect(items[1].total_findings).toBe(5);
    expect(jobStatusLabel('queued')).toBe('Queued');
  });
});

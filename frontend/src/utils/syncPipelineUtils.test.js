import {
  buildSyncPipelineToast,
  normalizeSyncProgressEntry,
  pickSyncProgressEntry,
  pipelineStageLabel,
  resolvePipelineUiStatus,
  resolveSyncProgressLabel,
  resolveStageDotState,
  syncProgressStageLabel,
  resolveSyncRetryHint,
} from './syncPipelineUtils';

describe('syncPipelineUtils', () => {
  test('pipelineStageLabel maps known stages', () => {
    expect(pipelineStageLabel('inventory')).toBe('Inventory');
    expect(pipelineStageLabel('analysis')).toBe('Analysis');
  });

  test('resolvePipelineUiStatus maps pipeline states', () => {
    expect(resolvePipelineUiStatus(null)).toBe('idle');
    expect(resolvePipelineUiStatus(null, { syncing: true })).toBe('running');
    expect(resolvePipelineUiStatus({ status: 'running', pending: true })).toBe('running');
    expect(resolvePipelineUiStatus({ status: 'completed' })).toBe('completed');
    expect(resolvePipelineUiStatus({ status: 'failed' })).toBe('failed');
  });

  test('syncProgressStageLabel uses sentence case', () => {
    expect(syncProgressStageLabel('cost', { status: 'running' }, { current_stage: 'cost' }))
      .toBe('Syncing costs…');
    expect(syncProgressStageLabel('inventory', { status: 'done' }, null))
      .toBe('Inventory complete');
  });

  test('resolveSyncProgressLabel covers running and failed states', () => {
    expect(resolveSyncProgressLabel(null, { syncing: true, uiStatus: 'running' }))
      .toBe('Starting sync…');
    expect(resolveSyncProgressLabel({
      status: 'running',
      message: 'Syncing costs…',
      current_stage: 'cost',
      stages: { cost: { status: 'running' } },
    }, { uiStatus: 'running' })).toBe('Syncing costs…');
    expect(resolveSyncProgressLabel({
      status: 'failed',
      current_stage: 'cost',
      stages: { cost: { status: 'failed' } },
    }, { uiStatus: 'failed' })).toBe('Costs failed');
  });

  test('normalizeSyncProgressEntry maps progress API fields', () => {
    const pipeline = normalizeSyncProgressEntry({
      pipeline_id: 'pipe-1',
      status: 'running',
      current_stage: 'metrics',
      percent_complete: 62,
      message: 'Syncing metrics…',
      stage_statuses: {
        inventory: { status: 'done' },
        cost: { status: 'done' },
        metrics: { status: 'running' },
        analysis: { status: 'pending' },
      },
      pending: true,
    });
    expect(pipeline.progress_pct).toBe(62);
    expect(pipeline.percent_complete).toBe(62);
    expect(pipeline.message).toBe('Syncing metrics…');
    expect(pipeline.stages.metrics.status).toBe('running');
    expect(pipeline.stage_statuses).toEqual(pipeline.stages);
  });

  test('pickSyncProgressEntry selects subscription row', () => {
    const payload = {
      subscriptions: [
        { subscription_id: 'aaa', pipeline_id: 'p1' },
        { subscription_id: 'bbb', pipeline_id: 'p2' },
      ],
    };
    expect(pickSyncProgressEntry(payload, 'bbb')?.pipeline_id).toBe('p2');
    expect(pickSyncProgressEntry(payload, 'missing')).toBeNull();
  });

  test('resolveStageDotState reflects stage row status', () => {
    expect(resolveStageDotState('inventory', { status: 'done' }, null)).toBe('done');
    expect(resolveStageDotState('metrics', { status: 'pending' }, { current_stage: 'metrics' }))
      .toBe('running');
  });

  test('resolveSyncRetryHint suggests retry on failure', () => {
    const hint = resolveSyncRetryHint({
      status: 'failed',
      current_stage: 'cost',
      stages: { cost: { status: 'failed', error: 'Timeout' } },
    });
    expect(hint).toMatch(/Sync failed/);
    expect(hint).toMatch(/Timeout/);
  });

  test('buildSyncPipelineToast reports success counts', () => {
    const { msg, isError } = buildSyncPipelineToast({
      status: 'completed',
      stages: {
        inventory: { status: 'done', result: { db_total: 12, resources: { 'compute/vm': 12 } } },
        cost: { status: 'done' },
        metrics: { status: 'done' },
        analysis: { status: 'done' },
      },
      analysis_job_id: 'job-1',
    });
    expect(isError).toBe(false);
    expect(msg).toMatch(/Synced 12 resources/);
    expect(msg).toMatch(/Analysis completed/);
  });

  test('buildSyncPipelineToast reports failed stage', () => {
    const { msg, isError } = buildSyncPipelineToast({
      status: 'failed',
      current_stage: 'cost',
      error: 'Cost API unavailable',
      stages: {
        inventory: { status: 'done' },
        cost: { status: 'failed', error: 'Cost API unavailable' },
      },
    });
    expect(isError).toBe(true);
    expect(msg).toMatch(/Costs/);
  });
});

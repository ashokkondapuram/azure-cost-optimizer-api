/** Helpers for unified sync pipeline progress and completion messaging. */

import { toDisplayText } from './formatDisplay';

export const PIPELINE_STAGES = ['inventory', 'cost', 'metrics', 'analysis'];

/** Normalize GET /sync/progress entry (or SSE progress payload) to pipeline shape. */
export function normalizeSyncProgressEntry(entry) {
  if (!entry) return null;
  const stages = entry.stage_statuses || entry.stages || {};
  const percent = entry.percent_complete ?? entry.progress_pct ?? 0;
  return {
    pipeline_id: entry.pipeline_id,
    status: entry.status,
    current_stage: entry.current_stage,
    progress_pct: percent,
    percent_complete: percent,
    stages,
    stage_statuses: stages,
    pending: entry.pending,
    error: entry.error,
    analysis_job_id: entry.analysis_job_id,
    started_at: entry.started_at,
    completed_at: entry.completed_at,
    message: entry.message,
  };
}

/** Pick one subscription row from GET /sync/progress or SSE snapshot payload. */
export function pickSyncProgressEntry(payload, subscriptionId) {
  if (!payload) return null;
  const rows = payload.subscriptions;
  if (!Array.isArray(rows) || !rows.length) return null;
  const target = (subscriptionId || '').toLowerCase();
  if (!target) return rows[0];
  return rows.find((row) => (row.subscription_id || '').toLowerCase() === target) || null;
}

const STAGE_LABELS = {
  inventory: 'Inventory',
  cost: 'Costs',
  metrics: 'Metrics',
  analysis: 'Analysis',
};

export function pipelineStageLabel(stage) {
  if (!stage || stage === 'completed') return 'Sync pipeline';
  return STAGE_LABELS[stage] || stage;
}

/** UI status for sync progress bar: idle | running | completed | failed */
export function resolvePipelineUiStatus(pipeline, { syncing = false } = {}) {
  if (syncing && !pipeline) return 'running';
  if (!pipeline) return 'idle';
  if (pipeline.status === 'failed') return 'failed';
  if (pipeline.status === 'completed') return 'completed';
  if (pipeline.pending || pipeline.status === 'queued' || pipeline.status === 'running') {
    return 'running';
  }
  return 'idle';
}

export function isPipelineActive(pipeline) {
  return resolvePipelineUiStatus(pipeline) === 'running';
}

/** Sentence-case label for a pipeline stage row. */
export function syncProgressStageLabel(stage, stageRow, pipeline) {
  const name = pipelineStageLabel(stage);
  const status = stageRow?.status;
  if (status === 'done') return `${name} complete`;
  if (status === 'failed') return `${name} failed`;
  if (status === 'skipped') return `${name} skipped`;
  if (status === 'running' || pipeline?.current_stage === stage) {
    return `Syncing ${name.toLowerCase()}…`;
  }
  return name;
}

/** Primary status line for the dashboard sync progress bar. */
export function resolveSyncProgressLabel(pipeline, { syncing = false, uiStatus } = {}) {
  const status = uiStatus || resolvePipelineUiStatus(pipeline, { syncing });
  if (status === 'idle') return '';
  if (pipeline?.message) return pipeline.message;
  if (syncing && !pipeline) return 'Starting sync…';
  if (status === 'completed') return 'Sync complete';
  if (status === 'failed') {
    const failedStage = pipeline?.current_stage;
    if (failedStage && failedStage !== 'completed') {
      return syncProgressStageLabel(failedStage, pipeline?.stages?.[failedStage], pipeline);
    }
    return 'Sync failed';
  }
  const currentStage = pipeline?.current_stage;
  if (currentStage && currentStage !== 'completed') {
    return syncProgressStageLabel(
      currentStage,
      pipeline?.stages?.[currentStage],
      pipeline,
    );
  }
  return 'Syncing…';
}

/** Dot state for stage indicators: pending | running | done | failed | skipped */
export function resolveStageDotState(stage, stageRow, pipeline) {
  const status = stageRow?.status || 'pending';
  if (status === 'done') return 'done';
  if (status === 'failed') return 'failed';
  if (status === 'skipped') return 'skipped';
  if (status === 'running' || pipeline?.current_stage === stage) return 'running';
  return 'pending';
}

export function resolveSyncRetryHint(pipeline) {
  if (!pipeline || pipeline.status !== 'failed') return '';
  const failedStage = pipeline.current_stage;
  const stageError = failedStage ? pipeline?.stages?.[failedStage]?.error : null;
  const detail = toDisplayText(stageError || pipeline.error || '');
  return detail
    ? `Sync failed. ${detail} Run sync again from the resource page or action centre.`
    : 'Sync failed. Run sync again from the resource page or action centre.';
}

export function buildSyncPipelineToast(pipeline, { advisorResult } = {}) {
  const inventoryResult = pipeline?.stages?.inventory?.result;
  const resourceCounts = inventoryResult?.resources || {};
  const armTotal = Object.values(resourceCounts).reduce((sum, n) => sum + (n || 0), 0);
  const dbTotal = inventoryResult?.db_total;
  const scopedTypes = inventoryResult?.types;
  let msg = '';
  let isError = false;

  if (pipeline?.status === 'failed') {
    const failedStage = pipeline.current_stage;
    const stageError = pipeline?.stages?.[failedStage]?.error;
    msg = `Sync failed during ${pipelineStageLabel(failedStage)}: ${toDisplayText(stageError || pipeline.error || 'Unknown error')}`;
    isError = true;
  } else if (pipeline?.stages?.inventory?.status === 'failed') {
    const stageError = pipeline.stages.inventory.error;
    msg = `Sync failed during Inventory: ${toDisplayText(stageError || pipeline.error || 'Unknown error')}`;
    isError = true;
  } else if (dbTotal === 0 || (dbTotal == null && armTotal === 0)) {
    msg = scopedTypes?.length
      ? 'Sync finished but nothing was saved for this resource type. Retry or check Azure permissions.'
      : 'Sync finished but nothing was saved to the database. Pages will load live from Azure until sync succeeds.';
    isError = true;
  } else if (scopedTypes?.length) {
    msg = `Synced ${armTotal.toLocaleString()} ${scopedTypes.length === 1 ? 'resource' : 'resources'} from Azure`;
  } else {
    msg = `Synced ${(dbTotal ?? armTotal).toLocaleString()} resources to the database`;
  }

  if (!isError && pipeline?.stages) {
    const doneStages = Object.entries(pipeline.stages)
      .filter(([, row]) => row.status === 'done')
      .map(([name]) => STAGE_LABELS[name] || name);
    if (doneStages.length) {
      msg += `. Pipeline: ${doneStages.join(' → ')}`;
    }
  }

  if (pipeline?.analysis_job_id) {
    msg += '. Analysis completed';
  }

  if (advisorResult?.error) {
    msg += `. Advisor sync failed: ${toDisplayText(advisorResult.error)}`;
    isError = true;
  } else if (advisorResult?.stored != null || advisorResult?.fetched != null) {
    const stored = advisorResult.stored ?? 0;
    const fetched = advisorResult.fetched ?? 0;
    if (fetched > 0) {
      msg += `. ${stored.toLocaleString()} Advisor recommendations saved`;
    }
  }

  return { msg, isError };
}

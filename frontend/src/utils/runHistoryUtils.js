const STATUS_LABELS = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
};

export function jobStatusTone(status) {
  if (status === 'running') return 'info';
  if (status === 'queued') return 'medium';
  if (status === 'completed') return 'low';
  if (status === 'failed') return 'critical';
  return 'medium';
}

export function jobStatusLabel(status, explicit) {
  if (explicit) return explicit;
  return STATUS_LABELS[status] || status || 'Unknown';
}

function itemTimestamp(run, job) {
  return job?.completed_at
    || job?.started_at
    || job?.created_at
    || run?.analyzed_at
    || null;
}

function mergeRunAndJob(run, job) {
  const status = job?.status || 'completed';
  return {
    key: run?.id || job?.id,
    runId: run?.id || job?.run_id || null,
    jobId: job?.id || null,
    status,
    statusLabel: jobStatusLabel(status, job?.status_label),
    analyzedAt: itemTimestamp(run, job),
    engine_version: job?.engine_version || run?.engine_version || 'standard',
    profile: job?.profile || run?.profile || 'default',
    scopeLabel: job?.scope_label || null,
    total_findings: run?.total_findings,
    total_savings_usd: run?.total_savings_usd,
    critical: run?.critical ?? run?.critical_count,
    high: run?.high ?? run?.high_count,
    components: job?.components || [],
    error_message: job?.error_message,
    progress_pct: job?.progress_pct,
    isActive: job?.is_active || status === 'queued' || status === 'running',
    run: run || null,
    job: job || null,
  };
}

/** Merge analysis jobs and optimization runs into one timeline (jobs are source of truth for status). */
export function buildRunHistoryItems(runs = [], jobs = []) {
  const runById = Object.fromEntries(runs.map((r) => [r.id, r]));
  const runIdsWithJob = new Set();
  const items = [];

  for (const job of jobs) {
    if (job.run_id) runIdsWithJob.add(job.run_id);
    const run = job.run_id ? runById[job.run_id] : null;
    items.push(mergeRunAndJob(run, job));
  }

  for (const run of runs) {
    if (runIdsWithJob.has(run.id)) continue;
    const job = run.job || null;
    items.push(mergeRunAndJob(run, job));
  }

  return items.sort((a, b) => {
    const ta = a.analyzedAt ? new Date(a.analyzedAt).getTime() : 0;
    const tb = b.analyzedAt ? new Date(b.analyzedAt).getTime() : 0;
    return tb - ta;
  });
}

export function componentStatusLabel(component) {
  const status = component?.status || 'pending';
  if (status === 'completed') return 'Completed';
  if (status === 'failed') return 'Failed';
  if (status === 'running') return 'Running';
  return 'Pending';
}

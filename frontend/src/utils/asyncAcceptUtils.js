/** Helpers for async accept POSTs (sync/analyze) with timeout recovery polling. */

export const SYNC_ACCEPT_TIMEOUT_MS = 30_000;
export const ANALYZE_ACCEPT_TIMEOUT_MS = 30_000;

export function isTimeoutError(error) {
  return error?.code === 'ECONNABORTED';
}

export function isSyncAcceptResponse(payload, httpStatus) {
  if (!payload || typeof payload !== 'object') return false;
  return Boolean(
    payload.async
    || httpStatus === 202
    || payload.pending
    || payload.status === 'accepted'
    || payload.pipeline?.pending
    || payload.pipeline?.status === 'queued'
    || payload.pipeline?.status === 'running',
  );
}

export function isAnalyzeAcceptResponse(payload) {
  if (!payload || typeof payload !== 'object') return false;
  return Boolean(
    payload.job_id
    || payload.id
    || payload.status === 'queued'
    || payload.is_active,
  );
}

export function normalizeSyncAcceptPayload(payload, httpStatus) {
  return {
    ...payload,
    httpStatus: httpStatus ?? payload?.httpStatus,
    async: Boolean(payload?.async || httpStatus === 202),
    status: payload?.status || (httpStatus === 202 ? 'accepted' : undefined),
  };
}

export function normalizeAnalyzeJobPayload(payload) {
  if (!payload) return null;
  if (payload.id) return payload;
  if (payload.job_id) return { ...payload, id: payload.job_id };
  return payload;
}

import {
  isAnalyzeAcceptResponse,
  isSyncAcceptResponse,
  isTimeoutError,
  normalizeAnalyzeJobPayload,
  normalizeSyncAcceptPayload,
} from './asyncAcceptUtils';

describe('asyncAcceptUtils', () => {
  it('detects axios timeout errors', () => {
    expect(isTimeoutError({ code: 'ECONNABORTED' })).toBe(true);
    expect(isTimeoutError({ code: 'ERR_NETWORK' })).toBe(false);
  });

  it('recognizes sync accept payloads', () => {
    expect(isSyncAcceptResponse({ status: 'accepted', pending: true }, 202)).toBe(true);
    expect(isSyncAcceptResponse({ pipeline: { status: 'running' } }, 200)).toBe(true);
    expect(isSyncAcceptResponse({ status: 'error' }, 500)).toBe(false);
  });

  it('recognizes analyze accept payloads', () => {
    expect(isAnalyzeAcceptResponse({ job_id: 'abc' })).toBe(true);
    expect(isAnalyzeAcceptResponse({ id: 'abc', status: 'queued' })).toBe(true);
    expect(isAnalyzeAcceptResponse({ status: 'failed' })).toBe(false);
  });

  it('normalizes sync and analyze payloads', () => {
    expect(normalizeSyncAcceptPayload({ status: 'accepted' }, 202).httpStatus).toBe(202);
    expect(normalizeAnalyzeJobPayload({ job_id: 'j1' }).id).toBe('j1');
  });
});

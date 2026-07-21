import { getStoredToken } from '../api/tokenStorage';
import { handleUnauthorized } from '../api/authSession';

function parseSseChunk(chunk) {
  const line = chunk.split('\n').find((l) => l.startsWith('data: '));
  if (!line) return null;
  try {
    return JSON.parse(line.slice(6));
  } catch {
    return null;
  }
}

/** Subscribe to analysis job SSE events for a subscription (fetch + ReadableStream). */
export async function subscribeJobEvents(subscriptionId, { onEvent, onError, onOpen, signal } = {}) {
  const token = getStoredToken();
  const url = `/api/events/jobs/${encodeURIComponent(subscriptionId)}`;
  const resp = await fetch(url, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  });
  if (!resp.ok) {
    if (resp.status === 401) {
      handleUnauthorized('job_events_401');
    }
    const err = new Error(`Job events unavailable (${resp.status})`);
    onError?.(err);
    throw err;
  }
  onOpen?.();
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const evt = parseSseChunk(part);
      if (evt) onEvent?.(evt);
    }
  }
}

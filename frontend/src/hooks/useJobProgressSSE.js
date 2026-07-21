import { useEffect, useRef, useState } from 'react';
import { getStoredToken } from '../api/tokenStorage';

function parseEventData(raw) {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Subscribe to analysis job progress via native EventSource.
 * Falls back gracefully when the stream is unavailable.
 */
export default function useJobProgressSSE(subscriptionId, {
  enabled = true,
  onEvent,
} = {}) {
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled || !subscriptionId) {
      setConnected(false);
      return undefined;
    }

    const token = getStoredToken();
    const qs = token ? `?access_token=${encodeURIComponent(token)}` : '';
    const url = `/api/events/jobs/${encodeURIComponent(subscriptionId)}${qs}`;
    const source = new EventSource(url);

    source.onopen = () => setConnected(true);
    source.onmessage = (message) => {
      setConnected(true);
      const evt = parseEventData(message.data);
      if (evt) onEventRef.current?.(evt);
    };
    source.onerror = () => setConnected(false);

    return () => {
      source.close();
      setConnected(false);
    };
  }, [subscriptionId, enabled]);

  return { connected };
}

import { useEffect, useRef, useState } from 'react';
import { subscribeJobEvents } from '../utils/jobEvents';

const DEFAULT_POLL_MS = 10_000;

/**
 * Subscribe to job SSE events with a required polling fallback.
 * Polling interval is configurable; callers should use a longer interval when idle.
 */
export default function useServerEvents(subscriptionId, {
  enabled = true,
  onJobEvent,
  onPoll,
  pollIntervalMs = DEFAULT_POLL_MS,
} = {}) {
  const [connected, setConnected] = useState(false);
  const onJobEventRef = useRef(onJobEvent);
  const onPollRef = useRef(onPoll);
  onJobEventRef.current = onJobEvent;
  onPollRef.current = onPoll;

  useEffect(() => {
    if (!enabled || !subscriptionId) {
      setConnected(false);
      return undefined;
    }

    const controller = new AbortController();
    setConnected(false);

    subscribeJobEvents(subscriptionId, {
      signal: controller.signal,
      onOpen: () => setConnected(true),
      onEvent: (evt) => {
        setConnected(true);
        onJobEventRef.current?.(evt);
      },
      onError: () => setConnected(false),
    })
      .catch(() => setConnected(false))
      .finally(() => setConnected(false));

    return () => {
      controller.abort();
      setConnected(false);
    };
  }, [subscriptionId, enabled]);

  useEffect(() => {
    if (!enabled || !subscriptionId) return undefined;
    const tick = () => onPollRef.current?.();
    tick();
    const timer = setInterval(tick, pollIntervalMs);
    return () => clearInterval(timer);
  }, [enabled, subscriptionId, pollIntervalMs]);

  return { connected };
}

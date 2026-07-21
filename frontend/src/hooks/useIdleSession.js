import { useEffect, useRef } from 'react';
import { refreshSession } from '../api/auth';
import {
  SESSION_IDLE_MS,
  SESSION_REFRESH_THROTTLE_MS,
} from '../config/session';

/** Immediate user intent — taps, keys, focus. */
const IMMEDIATE_ACTIVITY_EVENTS = [
  'mousedown',
  'keydown',
  'touchstart',
  'touchend',
  'click',
  'pointerdown',
  'pointerup',
  'focusin',
];

/** High-frequency events on mobile — throttled. */
const THROTTLED_ACTIVITY_EVENTS = ['scroll', 'touchmove', 'pointermove', 'wheel'];

const ACTIVITY_THROTTLE_MS = 750;

function isCoarsePointerDevice() {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(pointer: coarse)').matches;
}

/**
 * Sign out after inactivity. Tracks touch/pointer on mobile and enforces idle
 * when returning from a backgrounded tab or app switch.
 */
export default function useIdleSession({ enabled, onIdle }) {
  const idleTimerRef = useRef(null);
  const lastRefreshRef = useRef(0);
  const lastActivityRef = useRef(Date.now());
  const throttleTimerRef = useRef(null);
  const onIdleRef = useRef(onIdle);
  onIdleRef.current = onIdle;

  useEffect(() => {
    if (!enabled) return undefined;

    const logoutIfIdle = () => {
      const idleFor = Date.now() - lastActivityRef.current;
      if (idleFor >= SESSION_IDLE_MS) {
        onIdleRef.current?.();
        return true;
      }
      return false;
    };

    const resetIdleTimer = () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      idleTimerRef.current = setTimeout(() => {
        logoutIfIdle();
      }, SESSION_IDLE_MS);
    };

    const maybeRefreshToken = () => {
      const now = Date.now();
      if (now - lastRefreshRef.current < SESSION_REFRESH_THROTTLE_MS) return;
      lastRefreshRef.current = now;
      refreshSession().catch(() => {});
    };

    const recordActivity = ({ refresh = true } = {}) => {
      lastActivityRef.current = Date.now();
      resetIdleTimer();
      if (refresh) maybeRefreshToken();
    };

    const onImmediateActivity = () => {
      recordActivity({ refresh: true });
    };

    const onThrottledActivity = () => {
      if (throttleTimerRef.current) return;
      throttleTimerRef.current = setTimeout(() => {
        throttleTimerRef.current = null;
        recordActivity({ refresh: false });
      }, ACTIVITY_THROTTLE_MS);
    };

    const onVisibilityOrFocus = () => {
      if (document.visibilityState === 'hidden') {
        return;
      }
      if (logoutIfIdle()) return;
      resetIdleTimer();
    };

    const onPageShow = (event) => {
      if (event.persisted) {
        onVisibilityOrFocus();
      }
    };

    IMMEDIATE_ACTIVITY_EVENTS.forEach((event) => {
      window.addEventListener(event, onImmediateActivity, { passive: true });
    });
    THROTTLED_ACTIVITY_EVENTS.forEach((event) => {
      window.addEventListener(event, onThrottledActivity, { passive: true });
    });
    document.addEventListener('visibilitychange', onVisibilityOrFocus);
    window.addEventListener('focus', onVisibilityOrFocus);
    window.addEventListener('pageshow', onPageShow);

    // iOS can delay focus until after visibility; coarse pointers rely more on touch.
    if (isCoarsePointerDevice()) {
      document.addEventListener('gesturestart', onImmediateActivity, { passive: true });
    }

    recordActivity({ refresh: false });

    return () => {
      IMMEDIATE_ACTIVITY_EVENTS.forEach((event) => {
        window.removeEventListener(event, onImmediateActivity);
      });
      THROTTLED_ACTIVITY_EVENTS.forEach((event) => {
        window.removeEventListener(event, onThrottledActivity);
      });
      document.removeEventListener('visibilitychange', onVisibilityOrFocus);
      window.removeEventListener('focus', onVisibilityOrFocus);
      window.removeEventListener('pageshow', onPageShow);
      document.removeEventListener('gesturestart', onImmediateActivity);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      if (throttleTimerRef.current) clearTimeout(throttleTimerRef.current);
    };
  }, [enabled]);
}

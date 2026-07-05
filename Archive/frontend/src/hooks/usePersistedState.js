import { useState, useEffect, useCallback } from 'react';

/** Persist state in localStorage with JSON serialization. */
export default function usePersistedState(key, defaultValue) {
  const [state, setState] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw != null) return JSON.parse(raw);
    } catch { /* ignore */ }
    return defaultValue;
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch { /* ignore quota */ }
  }, [key, state]);

  const reset = useCallback(() => setState(defaultValue), [defaultValue]);

  return [state, setState, reset];
}

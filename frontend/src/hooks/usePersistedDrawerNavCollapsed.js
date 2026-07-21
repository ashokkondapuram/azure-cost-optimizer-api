import { useCallback } from 'react';
import usePersistedState from './usePersistedState';

const DEFAULT_COLLAPSED = false;

/** Persist drawer side-nav collapsed preference in localStorage. */
export default function usePersistedDrawerNavCollapsed(
  storageKey = 'finops-drawer-nav-collapsed',
) {
  const [collapsed, setCollapsed] = usePersistedState(storageKey, DEFAULT_COLLAPSED);
  const toggleCollapsed = useCallback(() => {
    setCollapsed((current) => !current);
  }, [setCollapsed]);
  return [collapsed, toggleCollapsed, setCollapsed];
}

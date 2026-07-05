import { useCallback, useMemo } from 'react';
import usePersistedState from './usePersistedState';

function presetId() {
  return `preset-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Save and restore named filter combinations in localStorage. */
export default function useFilterPresets(pageKey, currentFilters) {
  const [presets, setPresets] = usePersistedState(`filter-presets:${pageKey}`, []);

  const savePreset = useCallback((name) => {
    const trimmed = String(name || '').trim();
    if (!trimmed) return null;
    const entry = {
      id: presetId(),
      name: trimmed,
      filters: { ...currentFilters },
      savedAt: new Date().toISOString(),
    };
    setPresets((prev) => [entry, ...prev].slice(0, 20));
    return entry;
  }, [currentFilters, setPresets]);

  const deletePreset = useCallback((id) => {
    setPresets((prev) => prev.filter((p) => p.id !== id));
  }, [setPresets]);

  const sortedPresets = useMemo(
    () => [...presets].sort((a, b) => (b.savedAt || '').localeCompare(a.savedAt || '')),
    [presets],
  );

  return { presets: sortedPresets, savePreset, deletePreset };
}

import { useCallback, useMemo } from 'react';
import usePersistedState from './usePersistedState';

function defaultConfig(columns) {
  const keys = columns.map((c) => c.key);
  return { visible: keys, order: keys };
}

/** Persist column visibility and order per resource list page. */
export default function useColumnConfig(apiPath, columns) {
  const storageKey = `column-config:${apiPath || 'default'}`;
  const [config, setConfig, resetConfig] = usePersistedState(
    storageKey,
    defaultConfig(columns),
  );

  const visibleColumns = useMemo(() => {
    const visibleSet = new Set(config.visible || []);
    const orderMap = new Map((config.order || []).map((key, idx) => [key, idx]));
    return columns
      .filter((col) => visibleSet.has(col.key))
      .sort((a, b) => (orderMap.get(a.key) ?? 999) - (orderMap.get(b.key) ?? 999));
  }, [columns, config]);

  const toggleColumn = useCallback((key) => {
    setConfig((prev) => {
      const visible = new Set(prev.visible || []);
      if (visible.has(key)) {
        if (visible.size <= 1) return prev;
        visible.delete(key);
      } else {
        visible.add(key);
      }
      return { ...prev, visible: [...visible] };
    });
  }, [setConfig]);

  const moveColumn = useCallback((key, direction) => {
    setConfig((prev) => {
      const order = [...(prev.order || columns.map((c) => c.key))];
      const idx = order.indexOf(key);
      if (idx < 0) return prev;
      const swap = direction === 'up' ? idx - 1 : idx + 1;
      if (swap < 0 || swap >= order.length) return prev;
      [order[idx], order[swap]] = [order[swap], order[idx]];
      return { ...prev, order };
    });
  }, [columns, setConfig]);

  const restoreDefaults = useCallback(() => {
    resetConfig();
  }, [resetConfig]);

  return {
    visibleColumns,
    config,
    toggleColumn,
    moveColumn,
    restoreDefaults,
    allColumns: columns,
  };
}

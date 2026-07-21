import { useCallback } from 'react';
import usePersistedState from './usePersistedState';

const DEFAULT_SECTIONS = {
  cost_health: true,
  top_spend: true,
  optimization: true,
  insights: true,
};

export default function useDashboardSections(storageKey = 'finops-dashboard-sections') {
  const [sections, setSections] = usePersistedState(storageKey, DEFAULT_SECTIONS);

  const isExpanded = useCallback((id) => sections[id] !== false, [sections]);

  const toggleSection = useCallback((id) => {
    setSections((prev) => ({ ...prev, [id]: !(prev[id] !== false) }));
  }, [setSections]);

  const expandAll = useCallback(() => {
    setSections({ ...DEFAULT_SECTIONS });
  }, [setSections]);

  const collapseAll = useCallback(() => {
    setSections({
      cost_health: false,
      top_spend: false,
      optimization: false,
      insights: false,
    });
  }, [setSections]);

  return { isExpanded, toggleSection, expandAll, collapseAll };
}

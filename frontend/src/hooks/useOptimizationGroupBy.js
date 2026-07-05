import usePersistedState from './usePersistedState';

/** Shared group-by preference across optimization hub tabs. */
export default function useOptimizationGroupBy(defaultValue = 'resource_type') {
  return usePersistedState('optimization-hub:group-by', defaultValue);
}

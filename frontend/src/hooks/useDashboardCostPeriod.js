import { useCallback } from 'react';
import usePersistedState from './usePersistedState';
import {
  DEFAULT_DASHBOARD_COST_PERIOD,
  isValidDashboardCostPeriod,
} from '../utils/costTimespanUtils';

export default function useDashboardCostPeriod(storageKey = 'finops-dashboard-cost-period') {
  const [period, setPeriod] = usePersistedState(storageKey, DEFAULT_DASHBOARD_COST_PERIOD);
  const onPeriodChange = useCallback((value) => {
    setPeriod(isValidDashboardCostPeriod(value) ? value : DEFAULT_DASHBOARD_COST_PERIOD);
  }, [setPeriod]);
  return [period, onPeriodChange];
}

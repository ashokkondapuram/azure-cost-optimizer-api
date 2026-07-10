import { useCallback } from 'react';
import usePersistedState from './usePersistedState';
import useDashboardCostPeriods from './useDashboardCostPeriods';
import {
  DEFAULT_DASHBOARD_COST_PERIOD,
  isValidDashboardCostPeriod,
} from '../utils/costTimespanUtils';

export default function useDashboardCostPeriod(storageKey = 'finops-dashboard-cost-period') {
  const periodOptions = useDashboardCostPeriods();
  const [period, setPeriod] = usePersistedState(storageKey, DEFAULT_DASHBOARD_COST_PERIOD);
  const onPeriodChange = useCallback((value) => {
    setPeriod(isValidDashboardCostPeriod(value, periodOptions) ? value : DEFAULT_DASHBOARD_COST_PERIOD);
  }, [periodOptions, setPeriod]);
  return [period, onPeriodChange, periodOptions];
}

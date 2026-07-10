import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchCostTimeframes } from '../api/azure';
import {
  DASHBOARD_COST_PERIOD_OPTIONS,
  dashboardCostPeriodOptionsFromCatalog,
} from '../utils/costTimespanUtils';

/** Dashboard period presets from GET /costs/timeframes (static fallback). */
export default function useDashboardCostPeriods() {
  const { data } = useQuery({
    queryKey: ['cost-timeframes'],
    queryFn: fetchCostTimeframes,
    staleTime: 24 * 60 * 60_000,
  });

  return useMemo(() => {
    const catalog = data?.timeframes;
    if (catalog?.length) {
      return dashboardCostPeriodOptionsFromCatalog(catalog);
    }
    return DASHBOARD_COST_PERIOD_OPTIONS;
  }, [data]);
}

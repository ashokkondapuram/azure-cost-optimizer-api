import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchCostTimeframes } from '../api/azure';
import {
  COST_TIMEFRAME_OPTIONS,
  mapTimeframeCatalog,
} from '../config/costTimeframes';

/** Cost explorer presets from GET /costs/timeframes (static fallback when API unavailable). */
export default function useCostTimeframes() {
  const { data } = useQuery({
    queryKey: ['cost-timeframes'],
    queryFn: fetchCostTimeframes,
    staleTime: 24 * 60 * 60_000,
  });

  return useMemo(() => {
    const catalog = data?.timeframes;
    if (catalog?.length) {
      return mapTimeframeCatalog(catalog);
    }
    return COST_TIMEFRAME_OPTIONS;
  }, [data]);
}

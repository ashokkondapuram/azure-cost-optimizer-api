import api from './client';
import { buildCostQueryParams } from '../config/costTimeframes';

export function fetchCostComparison({
  subscription_id,
  current_timeframe = 'MonthToDate',
  compare_timeframe = 'TheLastMonth',
  current_from_date,
  current_to_date,
  compare_from_date,
  compare_to_date,
}) {
  const params = {
    subscription_id,
    current_timeframe,
    compare_timeframe,
  };
  if (current_timeframe === 'Custom') {
    if (current_from_date) params.current_from_date = current_from_date;
    if (current_to_date) params.current_to_date = current_to_date;
  }
  if (compare_timeframe === 'Custom') {
    if (compare_from_date) params.compare_from_date = compare_from_date;
    if (compare_to_date) params.compare_to_date = compare_to_date;
  }
  return api.get('/costs/comparison', { params }).then((r) => r.data);
}

export { buildCostQueryParams };

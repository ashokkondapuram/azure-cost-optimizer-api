import { formatIsoDate } from './format';

/** Build chart rows from GET /costs/resource-daily points. */
export function buildResourceSpendTrendChart(points = []) {
  return (points || [])
    .filter((row) => row?.date)
    .map((row) => ({
      date: String(row.date).slice(0, 10),
      dateLabel: formatIsoDate(String(row.date).slice(0, 10)),
      cost: Number(row.cost) || 0,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function hasSpendTrendData(chartData = []) {
  return chartData.some((row) => Number(row.cost) > 0);
}

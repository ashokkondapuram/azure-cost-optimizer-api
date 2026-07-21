/** Build cumulative MTD series for current vs prior month comparison charts. */

function pointCost(point) {
  return Number(point?.cost_billing ?? point?.cost_usd ?? 0) || 0;
}

function pointDate(point) {
  const raw = point?.date;
  if (!raw) return null;
  const text = String(raw).slice(0, 10);
  return text.length === 10 ? text : null;
}

function monthKey(dateStr) {
  return dateStr?.slice(0, 7) || '';
}

/**
 * @returns {{ series: Array<{label: string, mtd: number, priorMtd: number}>, comparison: object|null }}
 */
export function buildMtdComparisonSeries(dailyPoints = [], monthlyComparison = null) {
  if (!dailyPoints?.length) {
    return { series: [], comparison: monthlyComparison || null };
  }

  const today = new Date();
  const currentKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  const priorDate = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  const priorKey = `${priorDate.getFullYear()}-${String(priorDate.getMonth() + 1).padStart(2, '0')}`;

  const byDayCurrent = new Map();
  const byDayPrior = new Map();

  for (const point of dailyPoints) {
    const date = pointDate(point);
    if (!date) continue;
    const key = monthKey(date);
    const day = Number(date.slice(8, 10));
    if (key === currentKey) {
      byDayCurrent.set(day, (byDayCurrent.get(day) || 0) + pointCost(point));
    } else if (key === priorKey) {
      byDayPrior.set(day, (byDayPrior.get(day) || 0) + pointCost(point));
    }
  }

  const maxDay = Math.max(today.getDate(), ...byDayCurrent.keys(), ...byDayPrior.keys());
  let cumMtd = 0;
  let cumPrior = 0;
  const series = [];

  for (let day = 1; day <= maxDay; day += 1) {
    cumMtd += byDayCurrent.get(day) || 0;
    cumPrior += byDayPrior.get(day) || 0;
    series.push({
      label: `Day ${day}`,
      day,
      mtd: Math.round(cumMtd * 100) / 100,
      priorMtd: Math.round(cumPrior * 100) / 100,
    });
  }

  return { series, comparison: monthlyComparison || null };
}

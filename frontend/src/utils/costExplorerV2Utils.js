import { billingAmount } from './costCurrency';
import { formatDateRange, formatIsoDate } from './format';
import { buildSparklineGeometry, formatIsoCurrency } from './dashboardV2Utils';
import { costTimeframeLabel, defaultCompareTimeframe } from '../config/costTimeframes';

export const CE_PRESETS = [
  { key: '7d', label: 'Last 7 days', value: 'Last7Days' },
  { key: '30d', label: 'Last 30 days', value: 'Last30Days' },
  { key: 'mtd', label: 'Month to date', value: 'MonthToDate' },
  { key: 'ytd', label: 'YTD', value: 'ThisYear' },
  { key: 'lastMonth', label: 'Last month', value: 'TheLastMonth' },
  { key: 'custom', label: 'Custom', value: 'Custom' },
];

export const SERVICE_COLORS = [
  '#60a5fa', '#f87171', '#fbbf24', '#a78bfa', '#34d399', '#22d3ee', '#94a3b8',
];

export function parseCostRows(resp) {
  if (!resp) return [];
  const props = resp.properties || resp.data?.properties || resp.data || resp;
  const cols = (props.columns || []).map((c) => c.name);
  const rows = props.rows || [];
  return rows.map((r) => {
    const obj = {};
    cols.forEach((c, i) => { obj[c] = r[i]; });
    return obj;
  });
}

export function resourceNameFromId(resourceId = '') {
  const parts = String(resourceId).split('/');
  return parts[parts.length - 1] || resourceId || 'Unknown';
}

export function buildDailyPoints(rows, { periodStart, periodEnd } = {}) {
  return rows
    .filter((r) => r.UsageDate || r.BillingPeriodStartDate)
    .map((r) => ({
      date: String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 10),
      dateLabel: formatIsoDate(String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 10)),
      cost: billingAmount(r),
    }))
    .filter((r) => {
      if (!periodStart || !periodEnd) return true;
      return r.date >= periodStart && r.date <= periodEnd;
    })
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function buildCompareDailyPoints(current, compareRows) {
  if (!compareRows?.length) return current;
  const compare = compareRows
    .map((r) => ({
      date: String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 10),
      cost: billingAmount(r),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  return current.map((row, index) => {
    const cmp = compare[index];
    return {
      ...row,
      compareCost: cmp?.cost ?? null,
      compareDateLabel: cmp ? formatIsoDate(cmp.date) : null,
    };
  });
}

export function buildCumulativePoints(dailyPoints) {
  let running = 0;
  return dailyPoints.map((row) => {
    running += row.cost || 0;
    return { ...row, cumulative: running };
  });
}

export function buildServiceRows(svcRows) {
  return svcRows
    .map((r) => ({
      key: r.ServiceName || 'Unassigned',
      name: r.ServiceName || 'Unassigned',
      cost: billingAmount(r),
    }))
    .filter((r) => r.cost > 0)
    .sort((a, b) => b.cost - a.cost);
}

export function aggregateByField(resourceRows, field, total) {
  const map = new Map();
  resourceRows.forEach((r) => {
    const key = String(r[field] || 'Unassigned').trim() || 'Unassigned';
    const cost = billingAmount(r);
    if (!cost) return;
    map.set(key, (map.get(key) || 0) + cost);
  });
  const max = Math.max(...map.values(), 1);
  return [...map.entries()]
    .map(([key, cost], index) => ({
      key,
      name: key,
      cost,
      sharePct: total > 0 ? (cost / total) * 100 : 0,
      widthPct: Math.round((cost / max) * 100),
      color: SERVICE_COLORS[index % SERVICE_COLORS.length],
    }))
    .sort((a, b) => b.cost - a.cost);
}

export function breakdownInsight(tab, rows, total, currency) {
  if (!rows.length || !total) {
    return 'No spend data for this dimension in the selected period.';
  }
  const top = rows[0];
  const pct = Math.round((top.cost / total) * 10) / 10;
  const amount = formatIsoCurrency(top.cost, currency, { decimals: 0 });
  if (tab === 'service') {
    return `${top.name} accounts for ${pct}% of period spend — largest single service category (${amount}).`;
  }
  if (tab === 'rg') {
    return `${top.name} leads at ${amount} — ${pct}% of subscription spend in this period.`;
  }
  if (tab === 'region') {
    return `${top.name} accounts for ${pct}% of period spend across deployed resources.`;
  }
  return `Tag ${top.name} carries ${pct}% of subscription spend in this period.`;
}

export function buildResourceSpendRows(resourceRows, compareRows, total) {
  const compareMap = new Map();
  compareRows.forEach((r) => {
    const id = r.ResourceId || '';
    if (id) compareMap.set(id, billingAmount(r));
  });

  return resourceRows
    .map((r) => {
      const cost = billingAmount(r);
      const prior = compareMap.get(r.ResourceId) ?? null;
      const trendPct = prior > 0 ? ((cost - prior) / prior) * 100 : (cost > 0 ? null : 0);
      return {
        resourceId: r.ResourceId,
        name: resourceNameFromId(r.ResourceId),
        service: r.ServiceName || '—',
        resourceGroup: r.ResourceGroup || '—',
        resourceType: r.ResourceType || '',
        region: r.ResourceLocation || r.Location || '',
        cost,
        prior,
        trendPct,
        sharePct: total > 0 ? (cost / total) * 100 : 0,
      };
    })
    .filter((r) => r.cost > 0)
    .sort((a, b) => b.cost - a.cost);
}

export function periodDayCount(periodStart, periodEnd) {
  if (!periodStart || !periodEnd) return null;
  const start = new Date(`${periodStart}T00:00:00`);
  const end = new Date(`${periodEnd}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  return Math.max(1, Math.round((end - start) / 86400000) + 1);
}

export function projectedMonthEnd(total, daysElapsed, timeframe) {
  if (!total || !daysElapsed) return null;
  if (timeframe === 'MonthToDate' || timeframe === 'BillingMonthToDate') {
    return (total / daysElapsed) * 30;
  }
  return null;
}

export function trendBadgeLabel(delta, currency) {
  if (delta == null || delta === 0) return null;
  const arrow = delta < 0 ? '↓' : '↑';
  return `${arrow} ${formatIsoCurrency(Math.abs(delta), currency, { decimals: 0 })} vs prior period`;
}

export function trendPctLabel(pct) {
  if (pct == null || Number.isNaN(pct)) return '—';
  if (pct === 0) return '— 0%';
  const arrow = pct > 0 ? '↑' : '↓';
  return `${arrow} ${Math.abs(pct).toFixed(0)}%`;
}

export function trendClass(pct) {
  if (pct == null || pct === 0) return 'ce-trend--muted';
  return pct > 0 ? 'ce-trend--up' : 'ce-trend--down';
}

export function formatCompactCost(amount) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toFixed(0);
}

export function buildMomBars(monthlyRows) {
  const byMonth = new Map();
  monthlyRows.forEach((r) => {
    const raw = String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 7);
    if (!raw) return;
    byMonth.set(raw, (byMonth.get(raw) || 0) + billingAmount(r));
  });
  const entries = [...byMonth.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const lastSix = entries.slice(-6);
  const max = Math.max(...lastSix.map(([, v]) => v), 1);
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return lastSix.map(([ym, total], index) => {
    const monthIdx = Number(ym.split('-')[1]) - 1;
    const label = monthNames[monthIdx] || ym;
    const compact = total >= 1000 ? `${(total / 1000).toFixed(1)}K` : total.toFixed(0);
    return {
      key: ym,
      label,
      total,
      compact,
      heightPct: Math.round((total / max) * 100),
      isCurrent: index === lastSix.length - 1,
    };
  });
}

export function buildYtdMonthlyStacks(monthlyServiceRows) {
  const months = new Map();
  monthlyServiceRows.forEach((r) => {
    const ym = String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 7);
    if (!ym) return;
    const service = r.ServiceName || 'Other';
    const cost = billingAmount(r);
    if (!months.has(ym)) months.set(ym, new Map());
    const bucket = months.get(ym);
    bucket.set(service, (bucket.get(service) || 0) + cost);
  });

  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const entries = [...months.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const currentYm = new Date().toISOString().slice(0, 7);

  return entries.map(([ym, services]) => {
    const total = [...services.values()].reduce((s, v) => s + v, 0);
    const sorted = [...services.entries()].sort((a, b) => b[1] - a[1]);
    const top = sorted.slice(0, 3);
    const other = sorted.slice(3).reduce((s, [, v]) => s + v, 0);
    const segments = [
      ...top.map(([name, cost], i) => ({
        key: name,
        cost,
        heightPct: total > 0 ? Math.round((cost / total) * 100) : 0,
        className: ['compute', 'db', 'storage'][i] || 'other',
      })),
    ];
    if (other > 0) {
      segments.push({
        key: 'Other',
        cost: other,
        heightPct: total > 0 ? Math.round((other / total) * 100) : 0,
        className: 'other',
      });
    }
    const monthIdx = Number(ym.split('-')[1]) - 1;
    return {
      key: ym,
      label: monthNames[monthIdx] || ym,
      total,
      compact: total >= 1000 ? `${(total / 1000).toFixed(1)}K` : total.toFixed(0),
      segments,
      isCurrent: ym === currentYm,
    };
  });
}

export function resolveCompareTimeframe(timeframe) {
  return defaultCompareTimeframe(timeframe);
}

export function periodLabel(timeframe, options, periodStart, periodEnd) {
  if (periodStart && periodEnd) return formatDateRange(periodStart, periodEnd);
  return costTimeframeLabel(timeframe, options);
}

export function sparklineFromCosts(costs, width = 120, height = 28) {
  const points = costs.map((cost, i) => ({ date: String(i), cost }));
  return buildSparklineGeometry(points, width, height, 4);
}

/** True when cost explorer has enough data to render charts and tables. */
export function hasCostExplorerData({
  summary,
  dailyPoints,
  serviceRows,
  resourceRows,
  syncRequired,
} = {}) {
  if (syncRequired) return false;
  if (Number(summary?.pretax_total ?? summary?.cost_usd_total ?? 0) > 0) return true;
  if (dailyPoints?.length) return true;
  if (serviceRows?.length) return true;
  if (resourceRows?.length) return true;
  return false;
}

export { buildSparklineGeometry, formatIsoCurrency };

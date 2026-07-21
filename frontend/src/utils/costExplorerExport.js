import {
  fetchCosts,
  fetchCostByService,
  fetchCostByResource,
  fetchCostSummary,
} from '../api/azure';
import { billingAmount } from './costCurrency';

function parseCostRows(resp) {
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

function csvEscape(value) {
  const s = String(value ?? '').replace(/"/g, '""');
  return `"${s}"`;
}

function downloadCsv(filename, sections) {
  const lines = sections.flatMap((section) => {
    const out = [`# ${section.title}`];
    if (section.subtitle) out.push(`# ${section.subtitle}`);
    out.push(section.headers.map(csvEscape).join(','));
    section.rows.forEach((row) => {
      out.push(row.map(csvEscape).join(','));
    });
    out.push('');
    return out;
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Fetch cost data from API (prefer live Azure when requested) and export as CSV.
 */
export async function exportCostExplorerCsv({
  params,
  currency = 'CAD',
  preferLive = true,
  timeframeLabel = 'Period',
}) {
  const liveParams = { ...params, prefer_live: preferLive ? 'true' : undefined };

  const [summary, dailyResp, serviceResp, resourceResp] = await Promise.all([
    fetchCostSummary(liveParams),
    fetchCosts({ ...liveParams, granularity: 'Daily' }),
    fetchCostByService(liveParams),
    fetchCostByResource(liveParams),
  ]);

  const dailyRows = parseCostRows(dailyResp);
  const serviceRows = parseCostRows(serviceResp);
  const resourceRows = parseCostRows(resourceResp);

  const total = summary?.pretax_total
    ?? dailyRows.reduce((s, r) => s + billingAmount(r), 0);

  const sections = [
    {
      title: 'Summary',
      subtitle: `${timeframeLabel} · ${currency}`,
      headers: ['Metric', 'Value'],
      rows: [
        ['Period spend', total],
        ['Billing currency', summary?.billing_currency || currency],
        ['Services', serviceRows.length],
        ['Resources', resourceRows.length],
        ['Daily rows', dailyRows.length],
        ['Source', preferLive ? 'Azure (live when available)' : 'Database'],
        ['Synced at', summary?.synced_at || ''],
      ],
    },
    {
      title: 'Daily cost',
      headers: ['Date', 'PreTaxCost', 'CostUSD', 'Currency'],
      rows: dailyRows.map((r) => [
        r.UsageDate || r.BillingPeriodStartDate || '',
        billingAmount(r),
        r.CostUSD ?? '',
        r.Currency ?? currency,
      ]),
    },
    {
      title: 'Cost by service',
      headers: ['Service', 'PreTaxCost', 'CostUSD', 'Currency'],
      rows: serviceRows.map((r) => [
        r.ServiceName || 'Unassigned',
        billingAmount(r),
        r.CostUSD ?? '',
        r.Currency ?? currency,
      ]),
    },
    {
      title: 'Cost by resource',
      headers: ['ResourceId', 'ResourceType', 'ResourceGroup', 'Service', 'PreTaxCost', 'CostUSD'],
      rows: resourceRows.map((r) => [
        r.ResourceId || '',
        r.ResourceType || '',
        r.ResourceGroup || '',
        r.ServiceName || '',
        billingAmount(r),
        r.CostUSD ?? '',
      ]),
    },
  ];

  const stamp = new Date().toISOString().slice(0, 10);
  downloadCsv(`cost-explorer-${currency.toLowerCase()}-${stamp}.csv`, sections);

  return {
    dailyCount: dailyRows.length,
    serviceCount: serviceRows.length,
    resourceCount: resourceRows.length,
    total,
  };
}

export { parseCostRows };

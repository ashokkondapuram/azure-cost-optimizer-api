/**
 * Export Center
 *
 * A single page to pull any cost dataset and download it as CSV or JSON.
 *
 * Available exports:
 *   1. Cost by service    (/costs/by-service)
 *   2. Cost by type       (/costs/by-resource-type)
 *   3. Cost summary       (/costs/summary)
 *   4. Month-over-month   (/savings/month-over-month)
 *   5. Service breakdown  (/savings/service-breakdown)
 *   6. Advisor recs       (/reservations/recommendations)
 *
 * UI: dataset selector → params → Preview table → Download CSV / JSON
 */
import React, { useState, useCallback, useContext } from 'react';
import { Download, Eye, RefreshCw, AlertTriangle, FileText } from 'lucide-react';
import { fetchCostByService, fetchCostByResourceType, fetchCostSummary } from '../api/costAllocation';
import { fetchMonthOverMonth, fetchServiceBreakdown } from '../api/optimizationTimeline';
import { fetchReservationRecommendations } from '../api/reservationAdvisor';
import { toCsv, downloadCsv, downloadJson } from '../api/exportCenter';

let SubscriptionContext;
try { ({ SubscriptionContext } = require('../context/SubscriptionContext')); } catch { SubscriptionContext = null; }
function useCtxSub() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

const DATASETS = [
  { id: 'by-service',       label: 'Cost by service',           params: ['timeframe'] },
  { id: 'by-type',          label: 'Cost by resource type',     params: ['timeframe'] },
  { id: 'summary',          label: 'Cost summary',              params: ['timeframe'] },
  { id: 'mom',              label: 'Month-over-month savings',  params: ['months_back'] },
  { id: 'service-breakdown',label: 'Service breakdown (2 months)', params: ['base_month','compare_month'] },
  { id: 'ri-recs',          label: 'RI / Savings Plan recs',    params: ['commitment_type'] },
];

const TIMEFRAMES = ['MonthToDate','BillingMonthToDate','TheLastMonth','TheLastBillingMonth','WeekToDate'];

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

function PreviewTable({ rows, columns }) {
  if (!rows?.length) return <p className="text-sm text-gray-400 text-center py-8">No preview data</p>;
  const cols = columns ?? Object.keys(rows[0]);
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
            {cols.map((c) => (
              <th key={c} className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((row, i) => (
            <tr key={i} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750">
              {cols.map((c) => (
                <td key={c} className="px-3 py-1.5 text-gray-700 dark:text-gray-300 whitespace-nowrap tabular-nums">
                  {row[c] != null ? String(row[c]) : '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 50 && (
        <p className="text-center text-xs text-gray-400 py-2 border-t border-gray-100 dark:border-gray-700">
          Showing 50 of {rows.length} rows — full data included in download
        </p>
      )}
    </div>
  );
}

function normaliseRows(dataset, raw) {
  if (!raw) return [];
  if (dataset === 'mom') {
    return (raw.comparisons ?? []).map((c) => ({
      from_month: c.from_month, to_month: c.to_month,
      from_spend: c.from_spend, to_spend: c.to_spend,
      delta: c.delta, delta_pct: c.delta_pct, status: c.status, currency: c.currency,
    }));
  }
  if (dataset === 'service-breakdown') return raw.services ?? [];
  if (dataset === 'ri-recs') return raw.recommendations ?? [];
  if (dataset === 'summary') return [{ ...raw }];
  // by-service, by-type: unpack properties.rows
  const rows = raw?.properties?.rows ?? raw?.rows ?? [];
  const cols = (raw?.properties?.columns ?? raw?.columns ?? []).map((c) => c.name ?? c);
  if (!cols.length) return rows.map((r) => (typeof r === 'object' ? r : { value: r }));
  return rows.map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
}

export default function ExportCenter() {
  const ctxSub = useCtxSub();
  const [subId, setSubId] = useState(ctxSub ?? '');
  const [dataset, setDataset] = useState('by-service');
  const [timeframe, setTimeframe] = useState('MonthToDate');
  const [monthsBack, setMonthsBack] = useState(6);
  const [baseMonth, setBaseMonth] = useState('');
  const [compareMonth, setCompareMonth] = useState('');
  const [commitmentType, setCommitmentType] = useState('all');
  const [raw, setRaw] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const dsConfig = DATASETS.find((d) => d.id === dataset);

  const preview = useCallback(async () => {
    if (!subId.trim()) return;
    setLoading(true); setError(null); setRaw(null); setRows([]);
    try {
      let data;
      if (dataset === 'by-service')        data = await fetchCostByService(subId, { timeframe });
      else if (dataset === 'by-type')      data = await fetchCostByResourceType(subId, timeframe);
      else if (dataset === 'summary')      data = await fetchCostSummary(subId, { timeframe });
      else if (dataset === 'mom')          data = await fetchMonthOverMonth(subId, monthsBack);
      else if (dataset === 'service-breakdown') data = await fetchServiceBreakdown(subId, baseMonth, compareMonth);
      else if (dataset === 'ri-recs')      data = await fetchReservationRecommendations(subId, commitmentType);
      setRaw(data);
      setRows(normaliseRows(dataset, data));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [subId, dataset, timeframe, monthsBack, baseMonth, compareMonth, commitmentType]);

  const filename = `${dataset}-${subId.slice(0, 8)}-${new Date().toISOString().slice(0, 10)}`;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <Download size={20} className="text-teal-600" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">Export Center</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Preview any cost dataset and download as CSV or JSON.
        </p>
      </div>

      {/* Controls */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4 mb-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Subscription ID</label>
            <input type="text" value={subId} onChange={(e) => setSubId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Dataset</label>
            <select value={dataset} onChange={(e) => setDataset(e.target.value)}
              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500">
              {DATASETS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
            </select>
          </div>
        </div>

        {/* Dataset-specific params */}
        {dsConfig?.params.includes('timeframe') && (
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Timeframe</label>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}
              className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500">
              {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        )}
        {dsConfig?.params.includes('months_back') && (
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Months back</label>
            <div className="flex gap-2">
              {[3,6,9,12].map((n) => (
                <button key={n} onClick={() => setMonthsBack(n)}
                  className={`rounded-lg px-3 py-1 text-xs font-medium ${
                    monthsBack === n ? 'bg-teal-600 text-white' : 'border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}>{n}m</button>
              ))}
            </div>
          </div>
        )}
        {dsConfig?.params.includes('base_month') && (
          <div className="flex gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Base month</label>
              <input type="month" value={baseMonth} onChange={(e) => setBaseMonth(e.target.value)}
                className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Compare month</label>
              <input type="month" value={compareMonth} onChange={(e) => setCompareMonth(e.target.value)}
                className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500" />
            </div>
          </div>
        )}
        {dsConfig?.params.includes('commitment_type') && (
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Commitment type</label>
            <div className="flex gap-2">
              {['all','reserved_instance','savings_plan'].map((ct) => (
                <button key={ct} onClick={() => setCommitmentType(ct)}
                  className={`rounded-lg px-3 py-1 text-xs font-medium capitalize ${
                    commitmentType === ct ? 'bg-teal-600 text-white' : 'border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}>{ct.replace('_',' ')}</button>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <button onClick={preview} disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-1.5 text-sm font-medium text-white transition-colors">
            <Eye size={14} className={loading ? 'animate-pulse' : ''} />
            {loading ? 'Fetching…' : 'Preview'}
          </button>
          {rows.length > 0 && (
            <>
              <button onClick={() => downloadCsv(`${filename}.csv`, toCsv(rows))}
                className="flex items-center gap-1.5 rounded-lg border border-teal-200 dark:border-teal-700 text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-900/20 px-4 py-1.5 text-sm font-medium transition-colors">
                <Download size={14} /> CSV
              </button>
              <button onClick={() => downloadJson(`${filename}.json`, raw)}
                className="flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 px-4 py-1.5 text-sm font-medium transition-colors">
                <FileText size={14} /> JSON
              </button>
              <span className="text-xs text-gray-400">{rows.length} rows</span>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}
        </div>
      )}

      {loading && <Skeleton className="h-64 rounded-xl" />}
      {!loading && rows.length > 0 && <PreviewTable rows={rows} />}

      {!loading && !raw && !error && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500 gap-3">
          <Download size={40} strokeWidth={1.5} />
          <p className="text-sm font-medium">Select a dataset and click Preview</p>
        </div>
      )}
    </div>
  );
}

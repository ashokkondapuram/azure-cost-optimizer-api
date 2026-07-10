/**
 * Subscription Cost Allocation
 *
 * ┌─ Timeframe selector + KPI summary bar ─────────────────────────┐
 * ├─ Donut: cost by service (top 10)                               ┤
 * ├─ Table: cost by resource type (sortable)                       ┤
 * └─ Resource group drilldown (select RG → daily bar chart)        ┘
 *
 * Data: /costs/summary, /costs/by-service, /costs/by-resource-type,
 *       /costs/resource-group
 */
import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { Layers, DollarSign, ChevronDown } from 'lucide-react';
import {
  fetchCostSummary, fetchCostByService,
  fetchCostByResourceType,
} from '../api/costAllocation';
import { downloadCsv, toCsv } from '../api/exportCenter';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';

const fmt = (n, cur = 'CAD') =>
  n != null ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(n) : '—';

const PALETTE = ['#0d9488','#0891b2','#7c3aed','#db2777','#d97706','#16a34a','#dc2626','#ea580c','#9333ea','#0284c7'];

const TIMEFRAMES = ['MonthToDate','BillingMonthToDate','TheLastMonth','TheLastBillingMonth','WeekToDate','Custom'];

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

function KpiCard({ label, value, sub, icon: Icon, accent }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 shadow-sm">
      <div className={`mt-0.5 rounded-lg p-2 ${accent}`}><Icon size={16} /></div>
      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</p>
        <p className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">{value}</p>
        {sub && <p className="text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
      </div>
    </div>
  );
}

function ServiceDonut({ data, loading, currency }) {
  if (loading) return <Skeleton className="h-72 rounded-xl" />;
  if (!data?.length) return null;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4 mb-5">
      <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-4">Cost by service (top 10)</h2>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={60} outerRadius={100}
            dataKey="value" nameKey="name" paddingAngle={2}
          >
            {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Pie>
          <Tooltip formatter={(v) => fmt(v, currency)} />
          <Legend iconType="circle" iconSize={10} formatter={(v) => <span className="text-xs text-gray-600 dark:text-gray-300">{v}</span>} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function ResourceTypeTable({ data, loading, currency }) {
  const [sortDir, setSortDir] = useState('desc');
  const sorted = useMemo(() => {
    if (!data?.length) return [];
    return [...data].sort((a, b) => sortDir === 'desc' ? b.cost - a.cost : a.cost - b.cost);
  }, [data, sortDir]);

  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!sorted.length) return null;

  const maxCost = sorted[0]?.cost ?? 1;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden mb-5">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Cost by resource type</h2>
        <div className="flex items-center gap-2">
          <button onClick={() => setSortDir((d) => d === 'desc' ? 'asc' : 'desc')}
            className="text-xs text-gray-500 hover:text-teal-600 flex items-center gap-1">
            {sortDir === 'desc' ? 'Highest first' : 'Lowest first'}
            <ChevronDown size={12} className={sortDir === 'asc' ? 'rotate-180' : ''} />
          </button>
          <button onClick={() => {
            const rows = sorted.map((r) => ({ resource_type: r.name, cost: r.cost, currency }));
            downloadCsv(`cost-by-type-${new Date().toISOString().slice(0,10)}.csv`, toCsv(rows));
          }} className="text-xs text-teal-600 hover:underline">Export CSV</button>
        </div>
      </div>
      <div className="divide-y divide-gray-50 dark:divide-gray-800">
        {sorted.slice(0, 30).map((row, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-2">
            <span className="text-xs text-gray-600 dark:text-gray-300 w-56 shrink-0 truncate font-mono" title={row.name}>{row.name}</span>
            <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
              <div className="h-2 rounded-full bg-teal-500" style={{ width: `${(row.cost / maxCost) * 100}%` }} />
            </div>
            <span className="text-xs tabular-nums font-semibold text-gray-800 dark:text-gray-100 w-24 text-right shrink-0">{fmt(row.cost, currency)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CostAllocation() {
  const { subscription } = useAdvancedSubscription();
  const [timeframe, setTimeframe] = useState('MonthToDate');
  const [summary, setSummary] = useState(null);
  const [serviceData, setServiceData] = useState(null);
  const [typeData, setTypeData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    setLoading(true); setError(null);
    try {
      const [sum, svc, typ] = await Promise.all([
        fetchCostSummary(subscription, { timeframe }),
        fetchCostByService(subscription, { timeframe }),
        fetchCostByResourceType(subscription, timeframe),
      ]);
      setSummary(sum);

      // Parse by-service into { name, value }
      const svcRows = svc?.properties?.rows ?? svc?.rows ?? [];
      const svcCols = svc?.properties?.columns ?? svc?.columns ?? [];
      const nameIdx = svcCols.findIndex((c) => (c.name ?? c).toLowerCase().includes('service'));
      const costIdx = svcCols.findIndex((c) => (c.name ?? c).toLowerCase().includes('cost') || (c.name ?? c).toLowerCase().includes('usd'));
      const parsedSvc = svcRows
        .map((r) => ({ name: r[nameIdx] ?? r[0] ?? 'Unknown', value: parseFloat(r[costIdx] ?? r[1] ?? 0) }))
        .filter((r) => r.value > 0)
        .sort((a, b) => b.value - a.value)
        .slice(0, 10);
      setServiceData(parsedSvc);

      // Parse by-resource-type into { name, cost }
      const typRows = typ?.properties?.rows ?? typ?.rows ?? [];
      const typCols = typ?.properties?.columns ?? typ?.columns ?? [];
      const tNameIdx = typCols.findIndex((c) => (c.name ?? c).toLowerCase().includes('resource'));
      const tCostIdx = typCols.findIndex((c) => (c.name ?? c).toLowerCase().includes('cost') || (c.name ?? c).toLowerCase().includes('usd'));
      const parsedTyp = typRows
        .map((r) => ({ name: r[tNameIdx] ?? r[0] ?? 'Unknown', cost: parseFloat(r[tCostIdx] ?? r[2] ?? 0) }))
        .filter((r) => r.cost > 0);
      setTypeData(parsedTyp);
    } catch (e) { setError(e); }
    finally { setLoading(false); }
  }, [subscription, timeframe]);

  useEffect(() => {
    load();
  }, [load]);

  const currency = summary?.billing_currency ?? 'CAD';
  const totalCost = summary?.total_cost ?? summary?.totalCost ?? summary?.properties?.totalCost;

  return (
    <AdvancedToolLayout
      title="Cost allocation"
      subtitle="Subscription spend broken down by service, resource type, and resource group."
      iconKey="costAllocation"
      iconRoute="/cost-allocation"
      onRefresh={load}
      loading={loading}
      error={error}
      errorTitle="Could not load cost allocation"
    >
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}
          className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500">
          {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
        {loading ? Array.from({length:3}).map((_,i)=><Skeleton key={i} className="h-16 rounded-xl" />) : (
          <>
            <KpiCard label="Total spend" value={fmt(totalCost, currency)} sub={timeframe} icon={DollarSign}
              accent="bg-teal-100 text-teal-600 dark:bg-teal-900/40 dark:text-teal-400" />
            <KpiCard label="Services tracked" value={serviceData?.length ?? '—'} sub="top 10 shown in chart" icon={Layers}
              accent="bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400" />
            <KpiCard label="Resource types" value={typeData?.length ?? '—'} sub="with spend this period" icon={Layers}
              accent="bg-purple-100 text-purple-600 dark:bg-purple-900/40 dark:text-purple-400" />
          </>
        )}
      </div>

      <ServiceDonut data={serviceData} loading={loading} currency={currency} />
      <ResourceTypeTable data={typeData} loading={loading} currency={currency} />
    </AdvancedToolLayout>
  );
}

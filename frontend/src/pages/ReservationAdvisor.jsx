/**
 * Reservation Advisor — RI & Savings Plan recommendations
 *
 * ┌─ KPI bar: opportunity savings / underutilised count / VM spend ──┐
 * ├─ Commitment type filter (all / reserved_instance / savings_plan) ┤
 * ├─ Recommendation cards (sortable, ranked by annual savings)       ┤
 * └─ Underutilised commitments warning panel                         ┘
 *
 * Data: GET /reservations/coverage/{id}
 *       GET /reservations/recommendations/{id}
 */
import React, { useState, useCallback, useContext } from 'react';
import { BookMarked, DollarSign, AlertTriangle, TrendingDown, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { fetchReservationCoverage, fetchReservationRecommendations } from '../api/reservationAdvisor';

let SubscriptionContext;
try { ({ SubscriptionContext } = require('../context/SubscriptionContext')); } catch { SubscriptionContext = null; }
function useCtxSub() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

const fmt = (n, cur = 'CAD') =>
  n != null ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(n) : '—';

const COMMITMENT_BADGE = {
  reserved_instance: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  savings_plan:      'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
};
const SEVERITY_BADGE = {
  high:     'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  medium:   'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  low:      'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};

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

function RecCard({ rec, currency, expanded, onToggle }) {
  const annual = rec.estimated_annual_savings_usd ?? rec.estimated_monthly_savings_usd * 12;
  const monthly = rec.estimated_monthly_savings_usd;
  const ct = rec.scope === 'subscription' ? 'savings_plan'
    : rec.commitment_type ?? (rec.rule_id?.includes('SAVINGS') ? 'savings_plan' : 'reserved_instance');

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden">
      <button onClick={onToggle} className="w-full flex items-start justify-between px-4 py-3 text-left gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {rec.severity && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_BADGE[rec.severity?.toLowerCase()] ?? SEVERITY_BADGE.low}`}>
                {rec.severity}
              </span>
            )}
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${COMMITMENT_BADGE[ct] ?? 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
              {ct?.replace('_', ' ')}
            </span>
            <span className="font-medium text-sm text-gray-800 dark:text-gray-100 truncate">{rec.title}</span>
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-mono truncate" title={rec.resource_id}>{rec.resource_id}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-base font-bold tabular-nums text-teal-600 dark:text-teal-400">{fmt(annual, currency)}/yr</p>
          <p className="text-xs tabular-nums text-gray-400 dark:text-gray-500">{fmt(monthly, currency)}/mo</p>
        </div>
        {expanded ? <ChevronUp size={14} className="text-gray-400 mt-1 shrink-0" /> : <ChevronDown size={14} className="text-gray-400 mt-1 shrink-0" />}
      </button>
      {expanded && (
        <div className="border-t border-gray-50 dark:border-gray-700 px-4 py-3 space-y-2">
          {rec.detail && <p className="text-sm text-gray-600 dark:text-gray-300">{rec.detail}</p>}
          {rec.recommendation && (
            <div className="rounded-lg bg-teal-50 dark:bg-teal-900/20 border border-teal-100 dark:border-teal-800 px-3 py-2">
              <p className="text-xs font-semibold text-teal-700 dark:text-teal-300 mb-1">Recommendation</p>
              <p className="text-sm text-teal-800 dark:text-teal-200">{rec.recommendation}</p>
            </div>
          )}
          {rec.running_vm_count != null && (
            <p className="text-xs text-gray-500">Running VMs: <span className="font-semibold">{rec.running_vm_count}</span></p>
          )}
          {rec.scope && (
            <p className="text-xs text-gray-500">Scope: <span className="font-semibold capitalize">{rec.scope}</span></p>
          )}
        </div>
      )}
    </div>
  );
}

function UnderutilisedPanel({ items, currency }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/10 overflow-hidden mb-5">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-amber-100 dark:border-amber-800">
        <AlertTriangle size={14} className="text-amber-500" />
        <h2 className="text-sm font-semibold text-amber-800 dark:text-amber-200">Underutilised commitments</h2>
        <span className="ml-1 rounded-full bg-amber-200 dark:bg-amber-800 text-amber-800 dark:text-amber-200 px-2 py-0.5 text-xs font-medium">{items.length}</span>
      </div>
      <div className="divide-y divide-amber-50 dark:divide-amber-900/30">
        {items.map((item, i) => (
          <div key={i} className="flex items-center justify-between px-4 py-2.5 gap-4">
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-100">{item.title}</p>
              <p className="text-xs text-gray-400 font-mono truncate" title={item.resource_id}>{item.resource_id}</p>
            </div>
            <div className="text-right shrink-0">
              {item.utilisation_pct != null && (
                <p className="text-sm tabular-nums font-semibold text-amber-600">{item.utilisation_pct}% utilised</p>
              )}
              {item.wasted_usd > 0 && (
                <p className="text-xs tabular-nums text-red-500">{fmt(item.wasted_usd, currency)} wasted</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ReservationAdvisor() {
  const ctxSub = useCtxSub();
  const [subId, setSubId] = useState(ctxSub ?? '');
  const [commitmentType, setCommitmentType] = useState('all');
  const [coverage, setCoverage] = useState(null);
  const [recs, setRecs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});

  const load = useCallback(async () => {
    if (!subId.trim()) return;
    setLoading(true); setError(null);
    try {
      const [cov, rec] = await Promise.all([
        fetchReservationCoverage(subId),
        fetchReservationRecommendations(subId, commitmentType),
      ]);
      setCoverage(cov); setRecs(rec);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [subId, commitmentType]);

  const currency = coverage?.billing_currency ?? 'CAD';
  const recsItems = recs?.recommendations ?? [];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <BookMarked size={20} className="text-teal-600" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">Reservation Advisor</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          RI & Savings Plan purchase recommendations — ranked by annual savings opportunity.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <input
          type="text" value={subId} onChange={(e) => setSubId(e.target.value)}
          placeholder="Subscription ID"
          className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 w-80"
        />
        <div className="flex items-center gap-2">
          {['all', 'reserved_instance', 'savings_plan'].map((ct) => (
            <button key={ct}
              onClick={() => setCommitmentType(ct)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors capitalize ${
                commitmentType === ct
                  ? 'bg-teal-600 text-white'
                  : 'border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {ct.replace('_', ' ')}
            </button>
          ))}
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-1.5 text-sm font-medium text-white transition-colors">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Loading…' : 'Load'}
        </button>
      </div>

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
        {loading ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />) : (
          <>
            <KpiCard label="Annual opportunity" value={fmt(recs?.total_estimated_annual_savings_usd, currency)}
              sub={`${recs?.total_recommendations ?? '—'} recommendations`} icon={DollarSign}
              accent="bg-teal-100 text-teal-600 dark:bg-teal-900/40 dark:text-teal-400" />
            <KpiCard label="Monthly opportunity" value={fmt(coverage?.total_opportunity_savings_usd, currency)}
              sub="from open findings" icon={TrendingDown}
              accent="bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400" />
            <KpiCard label="Underutilised" value={coverage?.underutilised_commitments?.length ?? '—'}
              sub="active commitments" icon={AlertTriangle}
              accent="bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400" />
          </>
        )}
      </div>

      {/* Underutilised */}
      {!loading && <UnderutilisedPanel items={coverage?.underutilised_commitments} currency={currency} />}

      {/* Recommendation cards */}
      {!loading && recsItems.length > 0 && (
        <div className="mb-5">
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">
            Recommendations
            <span className="ml-2 text-xs font-normal text-gray-400">{recsItems.length} items — click to expand</span>
          </h2>
          <div className="space-y-2">
            {recsItems.map((rec, i) => (
              <RecCard key={i} rec={rec} currency={currency}
                expanded={!!expanded[i]}
                onToggle={() => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
              />
            ))}
          </div>
        </div>
      )}

      {loading && <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>}

      {!loading && !coverage && !error && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500 gap-3">
          <BookMarked size={40} strokeWidth={1.5} />
          <p className="text-sm font-medium">Enter a subscription ID and click Load</p>
        </div>
      )}
    </div>
  );
}

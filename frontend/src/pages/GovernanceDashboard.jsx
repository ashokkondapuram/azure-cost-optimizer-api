/**
 * Governance Dashboard
 *
 * ┌─ Score summary: tag compliance %, budget status, quota alerts ───┐
 * ├─ Tag compliance: overall score + per-tag coverage bars           ┤
 * ├─ Resource group compliance heat table                            ┤
 * ├─ Budget utilisation cards                                        ┤
 * └─ Quota near-limit warnings                                       ┘
 *
 * Data: /tag-compliance/score, /tag-compliance/groups,
 *       /costs/budgets, /security-posture/summary, /quota/summary
 */
import React, { useState, useCallback, useContext } from 'react';
import { Shield, Tag, DollarSign, AlertTriangle, RefreshCw, CheckCircle, XCircle } from 'lucide-react';
import {
  fetchTagComplianceScore, fetchTagComplianceGroups,
  fetchBudgets, fetchSecurityPosture, fetchQuotaSummary,
} from '../api/governanceDashboard';

let SubscriptionContext;
try { ({ SubscriptionContext } = require('../context/SubscriptionContext')); } catch { SubscriptionContext = null; }
function useCtxSub() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

function ScoreGauge({ pct, label }) {
  const colour = pct >= 80 ? '#0d9488' : pct >= 50 ? '#f59e0b' : '#ef4444';
  const r = 38; const circ = 2 * Math.PI * r;
  const dash = ((pct ?? 0) / 100) * circ;
  return (
    <div className="flex flex-col items-center">
      <svg width={96} height={96} viewBox="0 0 96 96">
        <circle cx={48} cy={48} r={r} fill="none" stroke="currentColor" strokeWidth={8}
          className="text-gray-100 dark:text-gray-700" />
        <circle cx={48} cy={48} r={r} fill="none" stroke={colour} strokeWidth={8}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          transform="rotate(-90 48 48)" style={{ transition: 'stroke-dasharray 0.6s ease' }} />
        <text x={48} y={54} textAnchor="middle" fontSize={18} fontWeight={700}
          fill={colour}>{pct != null ? `${pct}%` : '—'}</text>
      </svg>
      <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mt-1">{label}</p>
    </div>
  );
}

function TagCoverageBar({ tag, pct }) {
  const colour = pct >= 80 ? 'bg-teal-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-mono text-gray-600 dark:text-gray-300 w-32 shrink-0">{tag}</span>
      <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-2">
        <div className={`h-2 rounded-full ${colour} transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums font-semibold text-gray-700 dark:text-gray-300 w-10 text-right">{pct}%</span>
    </div>
  );
}

function RGHeatTable({ groups, loading }) {
  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!groups?.length) return null;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden mb-5">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Compliance by resource group</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700 text-left">
              {['Resource group', 'Resources', 'Compliant', 'Score'].map((h) => (
                <th key={h} className="px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const colour = g.score_pct >= 80 ? 'text-teal-600' : g.score_pct >= 50 ? 'text-amber-500' : 'text-red-500';
              return (
                <tr key={g.resource_group} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750">
                  <td className="px-4 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">{g.resource_group}</td>
                  <td className="px-4 py-2 tabular-nums text-gray-600 dark:text-gray-400">{g.total}</td>
                  <td className="px-4 py-2 tabular-nums text-gray-600 dark:text-gray-400">{g.compliant}</td>
                  <td className={`px-4 py-2 tabular-nums font-bold ${colour}`}>{g.score_pct}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BudgetCards({ budgets, loading }) {
  if (loading) return <Skeleton className="h-32 rounded-xl" />;
  const items = budgets?.value ?? budgets?.budgets ?? [];
  if (!items.length) return null;
  return (
    <div className="mb-5">
      <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">Budget utilisation</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map((b, i) => {
          const name = b.name ?? b.budget_name ?? `Budget ${i + 1}`;
          const amount = b.properties?.amount ?? b.amount ?? 0;
          const currentSpend = b.properties?.currentSpend?.amount ?? b.current_spend ?? 0;
          const pct = amount > 0 ? Math.round((currentSpend / amount) * 100) : null;
          const colour = pct == null ? 'text-gray-400' : pct >= 100 ? 'text-red-600' : pct >= 80 ? 'text-amber-500' : 'text-teal-600';
          return (
            <div key={i} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-100 mb-2">{name}</p>
              <div className="flex items-end justify-between mb-2">
                <span className={`text-2xl font-bold tabular-nums ${colour}`}>{pct != null ? `${pct}%` : '—'}</span>
                <span className="text-xs text-gray-400">{currentSpend.toLocaleString()} / {amount.toLocaleString()}</span>
              </div>
              <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-2 rounded-full ${pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-400' : 'bg-teal-500'}`}
                  style={{ width: `${Math.min(pct ?? 0, 100)}%`, transition: 'width 0.5s ease' }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function QuotaWarnings({ quota, loading }) {
  if (loading) return <Skeleton className="h-24 rounded-xl" />;
  const nearLimit = (quota?.by_resource_type ?? []).filter((q) => q.usage_pct >= 70);
  if (!nearLimit.length) return (
    <div className="flex items-center gap-2 rounded-xl border border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-900/10 px-4 py-3 mb-5">
      <CheckCircle size={15} className="text-teal-500" />
      <p className="text-sm text-teal-700 dark:text-teal-300">No quotas near limit</p>
    </div>
  );
  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/10 overflow-hidden mb-5">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-amber-100 dark:border-amber-800">
        <AlertTriangle size={14} className="text-amber-500" />
        <h2 className="text-sm font-semibold text-amber-800 dark:text-amber-200">Quota warnings</h2>
        <span className="ml-1 rounded-full bg-amber-200 dark:bg-amber-800 text-amber-800 dark:text-amber-200 px-2 py-0.5 text-xs font-medium">{nearLimit.length}</span>
      </div>
      <div className="divide-y divide-amber-50 dark:divide-amber-900/30">
        {nearLimit.map((q, i) => (
          <div key={i} className="flex items-center justify-between px-4 py-2.5 gap-4">
            <p className="text-sm text-gray-800 dark:text-gray-100">{q.resource_type ?? q.resource_type_display ?? 'Unknown'}</p>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500">{q.current_usage} / {q.limit}</span>
              <span className={`text-sm font-bold tabular-nums ${q.usage_pct >= 90 ? 'text-red-500' : 'text-amber-500'}`}>{q.usage_pct}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function GovernanceDashboard() {
  const ctxSub = useCtxSub();
  const [subId, setSubId] = useState(ctxSub ?? '');
  const [tagScore, setTagScore] = useState(null);
  const [tagGroups, setTagGroups] = useState(null);
  const [budgets, setBudgets] = useState(null);
  const [quota, setQuota] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!subId.trim()) return;
    setLoading(true); setError(null);
    try {
      const results = await Promise.allSettled([
        fetchTagComplianceScore(subId),
        fetchTagComplianceGroups(subId),
        fetchBudgets(subId),
        fetchQuotaSummary(subId),
      ]);
      if (results[0].status === 'fulfilled') setTagScore(results[0].value);
      if (results[1].status === 'fulfilled') setTagGroups(results[1].value);
      if (results[2].status === 'fulfilled') setBudgets(results[2].value);
      if (results[3].status === 'fulfilled') setQuota(results[3].value);
      const failed = results.filter((r) => r.status === 'rejected');
      if (failed.length === results.length) throw new Error(failed[0].reason?.message ?? 'All requests failed');
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [subId]);

  const hasData = tagScore || tagGroups || budgets || quota;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <Shield size={20} className="text-teal-600" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">Governance Dashboard</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Tag compliance, budget utilisation, quota health, and security posture — in one view.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-5">
        <input type="text" value={subId} onChange={(e) => setSubId(e.target.value)}
          placeholder="Subscription ID"
          className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 w-80"
        />
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

      {/* Tag compliance gauge + tag bars */}
      {(loading || tagScore) && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4 mb-5">
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-4">Tag compliance</h2>
          {loading ? <Skeleton className="h-32" /> : (
            <div className="flex flex-col md:flex-row items-start gap-8">
              <ScoreGauge pct={tagScore?.score_pct} label="Overall score" />
              <div className="flex-1 space-y-3">
                {Object.entries(tagScore?.tag_coverage_pct ?? {}).map(([tag, pct]) => (
                  <TagCoverageBar key={tag} tag={tag} pct={pct} />
                ))}
                <p className="text-xs text-gray-400 mt-2">
                  {tagScore?.fully_compliant} / {tagScore?.total_resources} resources fully compliant
                  {tagScore?.non_compliant_count > 0 && ` · ${tagScore.non_compliant_count} need tags`}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      <RGHeatTable groups={tagGroups?.groups} loading={loading} />
      <BudgetCards budgets={budgets} loading={loading} />
      <QuotaWarnings quota={quota} loading={loading} />

      {!loading && !hasData && !error && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500 gap-3">
          <Shield size={40} strokeWidth={1.5} />
          <p className="text-sm font-medium">Enter a subscription ID and click Load</p>
        </div>
      )}
    </div>
  );
}

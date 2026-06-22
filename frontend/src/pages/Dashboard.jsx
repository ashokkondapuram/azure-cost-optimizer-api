import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { DollarSign, Activity, AlertTriangle, TrendingDown, RefreshCw, Play } from 'lucide-react';
import { AppCtx } from '../App';
import { fetchFindingsSummary, fetchRuns, runAnalysis } from '../api/azure';

const SEV_COLORS = { CRITICAL: '#dc2626', HIGH: '#ef4444', MEDIUM: '#f59e0b', LOW: '#10b981', INFO: '#6366f1' };
const CAT_COLORS = ['#2563eb','#7c3aed','#0891b2','#059669','#d97706','#dc2626','#6366f1','#0d9488'];

export default function Dashboard() {
  const { subscription } = useContext(AppCtx);
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState('');

  const { data: summary, refetch: refetchSummary } = useQuery({
    queryKey: ['findings-summary', subscription],
    queryFn: () => fetchFindingsSummary({ subscription_id: subscription }),
    enabled: !!subscription,
  });

  const { data: runs } = useQuery({
    queryKey: ['runs', subscription],
    queryFn: () => fetchRuns({ subscription_id: subscription, limit: 10 }),
    enabled: !!subscription,
  });

  const handleRun = async () => {
    if (!subscription) return;
    setRunning(true); setRunMsg('');
    try {
      const r = await runAnalysis({ subscription_id: subscription, profile: 'default', include_metrics: false });
      setRunMsg(`✓ Run complete — ${r.summary?.total_findings ?? 0} findings, $${(r.summary?.total_estimated_monthly_savings_usd ?? 0).toLocaleString()} potential savings/mo`);
      refetchSummary();
    } catch (e) {
      setRunMsg(`✗ ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  const sev = summary?.by_severity || {};
  const cat = summary?.by_category || {};
  const sevData = Object.entries(sev).map(([k, v]) => ({ name: k, value: v }));
  const catData = Object.entries(cat).map(([k, v]) => ({ name: k, value: v }));
  const runsData = (runs || []).slice().reverse().map(r => ({
    date: new Date(r.analyzed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    savings: r.total_savings_usd,
    findings: r.total_findings,
  }));

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Dashboard</div>
          <div className="page-sub">Real-time Azure cost optimization · All data from live APIs</div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          {runMsg && <span style={{ fontSize: '0.82rem', color: runMsg.startsWith('✓') ? 'var(--success)' : 'var(--danger)' }}>{runMsg}</span>}
          <button className="btn btn-primary" onClick={handleRun} disabled={running || !subscription}>
            {running ? <div className="spin" /> : <Play size={14} />}
            {running ? 'Analyzing…' : 'Run Analysis'}
          </button>
        </div>
      </div>

      {!subscription && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
          <AlertTriangle size={32} style={{ margin: '0 auto 1rem', opacity: 0.4 }} />
          <p>Select a subscription from the sidebar to begin.</p>
        </div>
      )}

      {subscription && (
        <>
          {/* KPI row */}
          <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
            <div className="stat-card success">
              <div className="stat-label">Est. Monthly Savings</div>
              <div className="stat-value" style={{ color: 'var(--success)' }}>
                ${((summary?.total_estimated_savings_usd || 0)).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
              <div className="stat-sub">Open findings only</div>
            </div>
            <div className="stat-card danger">
              <div className="stat-label">Critical Findings</div>
              <div className="stat-value" style={{ color: 'var(--danger)' }}>{sev.CRITICAL || 0}</div>
              <div className="stat-sub">Require immediate action</div>
            </div>
            <div className="stat-card warning">
              <div className="stat-label">High Findings</div>
              <div className="stat-value" style={{ color: 'var(--warning)' }}>{sev.HIGH || 0}</div>
              <div className="stat-sub">Review within 7 days</div>
            </div>
            <div className="stat-card accent">
              <div className="stat-label">Total Open</div>
              <div className="stat-value">{summary?.open_findings || 0}</div>
              <div className="stat-sub">Across all categories</div>
            </div>
          </div>

          {/* Charts row */}
          <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
            <div className="card">
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Findings by Severity</div>
              {sevData.length === 0 ? <div className="empty-state" style={{ padding: '2rem' }}>No data — run analysis first</div> : (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={sevData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={75} label={({ name, value }) => `${name}: ${value}`}>
                      {sevData.map(e => <Cell key={e.name} fill={SEV_COLORS[e.name] || '#6366f1'} />)}
                    </Pie>
                    <Tooltip formatter={(v) => [v, 'Findings']} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="card">
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Findings by Category</div>
              {catData.length === 0 ? <div className="empty-state" style={{ padding: '2rem' }}>No data — run analysis first</div> : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={catData} margin={{ top: 0, right: 0, bottom: 20, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="name" tick={{ fill: 'var(--text3)', fontSize: 11 }} angle={-25} textAnchor="end" />
                    <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }} />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {catData.map((e, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Savings trend */}
          {runsData.length > 0 && (
            <div className="card">
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Savings Trend (Last Runs)</div>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={runsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                  <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }} formatter={v => [`$${v.toLocaleString()}`, 'Savings USD']} />
                  <Line type="monotone" dataKey="savings" stroke="#10b981" strokeWidth={2} dot={{ fill: '#10b981' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}

import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line
} from 'recharts';
import {
  Play, AlertTriangle, TrendingDown, Cpu, HardDrive,
  Network, Database, Shield, Boxes, Cloud, DollarSign, Activity
} from 'lucide-react';
import { AppCtx } from '../App';
import {
  fetchFindingsSummary, fetchRuns, runAnalysis,
  fetchVMs, fetchDisks, fetchAKS, fetchStorage,
  fetchPublicIPs, fetchSQL, fetchKeyVaults,
} from '../api/azure';
import api from '../api/client';

const SEV_COLORS = {
  CRITICAL: '#dc2626', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#22c55e', INFO: '#6366f1'
};
const CAT_COLORS = ['#2563eb','#7c3aed','#0891b2','#059669','#d97706','#dc2626','#6366f1','#0d9488'];

const fetchAllResources = (sub) => Promise.allSettled([
  fetchVMs({ subscription_id: sub }),
  fetchDisks({ subscription_id: sub }),
  fetchAKS({ subscription_id: sub }),
  fetchStorage({ subscription_id: sub }),
  fetchPublicIPs({ subscription_id: sub }),
  fetchSQL({ subscription_id: sub }),
  fetchKeyVaults({ subscription_id: sub }),
  api.get('/resources/appservices',    { params: { subscription_id: sub } }).then(r => r.data),
  api.get('/resources/loadbalancers',  { params: { subscription_id: sub } }).then(r => r.data),
  api.get('/resources/cosmosdb',       { params: { subscription_id: sub } }).then(r => r.data),
  api.get('/resources/postgresql',     { params: { subscription_id: sub } }).then(r => r.data),
  api.get('/resources/nsgs',           { params: { subscription_id: sub } }).then(r => r.data),
  api.get('/resources/acr',            { params: { subscription_id: sub } }).then(r => r.data),
  api.get('/resources/appgateways',    { params: { subscription_id: sub } }).then(r => r.data),
]);

const count = (result) => {
  if (result.status !== 'fulfilled') return 0;
  const d = result.value;
  if (Array.isArray(d)) return d.length;
  if (d?.value && Array.isArray(d.value)) return d.value.length;
  return 0;
};

export default function Dashboard() {
  const { subscription } = useContext(AppCtx);
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg]   = useState('');

  const { data: summary, refetch: refetchSummary } = useQuery({
    queryKey: ['findings-summary', subscription],
    queryFn:  () => fetchFindingsSummary({ subscription_id: subscription }),
    enabled:  !!subscription,
  });

  const { data: runs = [] } = useQuery({
    queryKey: ['runs', subscription],
    queryFn:  () => fetchRuns({ subscription_id: subscription, limit: 10 }),
    enabled:  !!subscription,
  });

  const { data: resources } = useQuery({
    queryKey: ['all-resources-counts', subscription],
    queryFn:  () => fetchAllResources(subscription),
    enabled:  !!subscription,
    staleTime: 5 * 60_000,
  });

  const { data: costByService } = useQuery({
    queryKey: ['cost-by-service', subscription],
    queryFn:  () => api.get('/costs/by-service', { params: { subscription_id: subscription } }).then(r => r.data),
    enabled:  !!subscription,
  });

  const handleRun = async () => {
    if (!subscription) return;
    setRunning(true); setRunMsg('');
    try {
      const r = await runAnalysis({ subscription_id: subscription, profile: 'default', include_metrics: false });
      setRunMsg('\u2713 ' + (r.summary?.total_findings ?? 0) + ' findings \u00b7 $' + ((r.summary?.total_estimated_monthly_savings_usd ?? 0)).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' potential savings/mo');
      refetchSummary();
    } catch (e) {
      setRunMsg('\u2717 ' + (e.response?.data?.detail || e.message));
    } finally {
      setRunning(false);
    }
  };

  // KPI data from live findings summary
  const sev = summary?.by_severity || {};
  const cat = summary?.by_category  || {};
  const sevData = Object.entries(sev).map(([k, v]) => ({ name: k, value: v }));
  const catData = Object.entries(cat).map(([k, v]) => ({ name: k, value: v }));

  // Cost trend from real runs
  const runsData = [...(runs || [])].reverse().map(r => ({
    date:     new Date(r.analyzed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    savings:  r.total_savings_usd || 0,
    findings: r.total_findings || 0,
  }));

  // Cost by service from real Azure Cost Management API
  const svcData = (() => {
    const rows = costByService?.properties?.rows || [];
    const cols = (costByService?.properties?.columns || []).map(c => c.name);
    const svcIdx  = cols.indexOf('ServiceName');
    const costIdx = cols.indexOf('PreTaxCost');
    if (svcIdx < 0 || costIdx < 0) return [];
    const map = {};
    rows.forEach(r => { map[r[svcIdx]] = (map[r[svcIdx]] || 0) + r[costIdx]; });
    return Object.entries(map)
      .map(([name, value]) => ({ name, value: Math.round(value) }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 8);
  })();

  // Resource category tiles
  const [vms, disks, aks, storage, ips, sql, kv, apps, lbs, cosmos, pg, nsgs, acr, agw] = resources || [];
  const resourceCategories = [
    {
      label: 'Compute',
      icon:  <Cpu size={18} />,
      color: '#3b82f6',
      items: [
        { name: 'Virtual Machines', count: count(vms),   link: '/vms' },
        { name: 'Managed Disks',    count: count(disks), link: '/resources' },
      ],
    },
    {
      label: 'Containers',
      icon:  <Boxes size={18} />,
      color: '#7c3aed',
      items: [
        { name: 'AKS Clusters',          count: count(aks), link: '/aks' },
        { name: 'Container Registries',  count: count(acr), link: '/resources' },
      ],
    },
    {
      label: 'App Services',
      icon:  <Cloud size={18} />,
      color: '#0891b2',
      items: [
        { name: 'Web / Function Apps', count: count(apps), link: '/resources' },
      ],
    },
    {
      label: 'Storage',
      icon:  <HardDrive size={18} />,
      color: '#d97706',
      items: [
        { name: 'Storage Accounts', count: count(storage), link: '/resources' },
      ],
    },
    {
      label: 'Networking',
      icon:  <Network size={18} />,
      color: '#059669',
      items: [
        { name: 'Public IPs',          count: count(ips),  link: '/resources' },
        { name: 'Load Balancers',       count: count(lbs),  link: '/resources' },
        { name: 'App Gateways',         count: count(agw),  link: '/resources' },
        { name: 'Network Sec. Groups',  count: count(nsgs), link: '/resources' },
      ],
    },
    {
      label: 'Databases',
      icon:  <Database size={18} />,
      color: '#dc2626',
      items: [
        { name: 'SQL Servers',    count: count(sql),    link: '/resources' },
        { name: 'Cosmos DB',      count: count(cosmos), link: '/resources' },
        { name: 'PostgreSQL',     count: count(pg),     link: '/resources' },
      ],
    },
    {
      label: 'Security',
      icon:  <Shield size={18} />,
      color: '#f97316',
      items: [
        { name: 'Key Vaults', count: count(kv), link: '/resources' },
      ],
    },
  ];

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">Dashboard</div>
          <div className="page-sub">Live Azure data &middot; no mocks &middot; {subscription || 'no subscription selected'}</div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          {runMsg && (
            <span style={{ fontSize: '0.82rem', color: runMsg.startsWith('\u2713') ? 'var(--success)' : 'var(--danger)' }}>
              {runMsg}
            </span>
          )}
          <button className="btn btn-primary" onClick={handleRun} disabled={running || !subscription}>
            {running ? <div className="spin" style={{ width: 14, height: 14, borderWidth: 2 }} /> : <Play size={14} />}
            {running ? 'Analyzing\u2026' : 'Run Analysis'}
          </button>
        </div>
      </div>

      {!subscription && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
          <AlertTriangle size={32} style={{ margin: '0 auto 1rem', display: 'block', opacity: 0.4 }} />
          <p>Select a subscription from the sidebar to begin.</p>
        </div>
      )}

      {subscription && (
        <>
          {/* KPI row — all from live findings summary API */}
          <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
            <div className="stat-card success">
              <div className="stat-label">Est. Monthly Savings</div>
              <div className="stat-value" style={{ color: 'var(--success)' }}>
                ${ (summary?.total_estimated_savings_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }) }
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

          {/* Resource category tiles — live counts from Azure ARM APIs */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.85rem', color: 'var(--text2)' }}>
              Azure Resources by Category
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.85rem' }}>
              {resourceCategories.map(cat => (
                <div key={cat.label} className="card" style={{ padding: '1rem 1.25rem', marginBottom: 0, borderTop: '3px solid ' + cat.color }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: '0.65rem', color: cat.color }}>
                    {cat.icon}
                    <span style={{ fontWeight: 700, fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{cat.label}</span>
                  </div>
                  {cat.items.map(item => (
                    <div key={item.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '3px 0', borderBottom: '1px solid var(--border)' }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text2)' }}>{item.name}</span>
                      <span style={{ fontSize: '0.9rem', fontWeight: 700, color: item.count > 0 ? 'var(--text)' : 'var(--text3)' }}>
                        {resources ? item.count : <span style={{ opacity: 0.4 }}>...</span>}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* Charts row */}
          <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
            <div className="card">
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Open Findings by Severity</div>
              {sevData.length === 0 ? (
                <div className="empty-state" style={{ padding: '2rem' }}>
                  <AlertTriangle size={24} />
                  <p style={{ fontSize: '0.82rem' }}>No data &mdash; run analysis first</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={sevData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={78}
                      label={({ name, value }) => name + ': ' + value}>
                      {sevData.map(e => <Cell key={e.name} fill={SEV_COLORS[e.name] || '#6366f1'} />)}
                    </Pie>
                    <Tooltip
                      formatter={(v) => [v, 'Findings']}
                      contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="card">
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Open Findings by Category</div>
              {catData.length === 0 ? (
                <div className="empty-state" style={{ padding: '2rem' }}>
                  <AlertTriangle size={24} />
                  <p style={{ fontSize: '0.82rem' }}>No data &mdash; run analysis first</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={catData} margin={{ top: 0, right: 0, bottom: 24, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="name" tick={{ fill: 'var(--text3)', fontSize: 11 }} angle={-25} textAnchor="end" />
                    <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }} />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {catData.map((e, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Cost by Azure service — live from Cost Management API */}
          {svcData.length > 0 && (
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>MTD Cost by Azure Service (live)</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={svcData} margin={{ top: 0, right: 0, bottom: 40, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="name" tick={{ fill: 'var(--text3)', fontSize: 11 }} angle={-30} textAnchor="end" />
                  <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} tickFormatter={v => '$' + (v >= 1000 ? (v/1000).toFixed(0) + 'k' : v)} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }}
                    formatter={v => ['$' + v.toLocaleString(), 'Cost']}
                  />
                  <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]}>
                    {svcData.map((_, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Savings trend across runs — live */}
          {runsData.length > 0 && (
            <div className="card">
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Savings Trend Across Analysis Runs (live)</div>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={runsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                  <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} tickFormatter={v => '$' + v.toLocaleString()} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }}
                    formatter={v => ['$' + v.toLocaleString(), 'Savings USD']}
                  />
                  <Line type="monotone" dataKey="savings" stroke="#22c55e" strokeWidth={2} dot={{ fill: '#22c55e' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}

import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LineChart, Line, Legend
} from 'recharts';
import { AppCtx } from '../App';
import { fetchCosts, fetchCostByService, fetchForecast, fetchBudgets } from '../api/azure';

const COLORS = ['#2563eb','#7c3aed','#0891b2','#059669','#d97706','#dc2626','#6366f1','#0d9488','#be185d','#b45309'];

function parseCostRows(resp) {
  if (!resp) return [];
  const props = resp.properties || resp;
  const cols  = (props.columns || []).map(c => c.name);
  const rows  = props.rows || [];
  return rows.map(r => {
    const obj = {};
    cols.forEach((c, i) => { obj[c] = r[i]; });
    return obj;
  });
}

export default function CostExplorer() {
  const { subscription } = useContext(AppCtx);
  const [timeframe, setTimeframe] = useState('MonthToDate');

  const { data: costData, isLoading: loadCost } = useQuery({
    queryKey: ['costs', subscription, timeframe],
    queryFn:  () => fetchCosts({ subscription_id: subscription, timeframe, granularity: 'Daily' }),
    enabled:  !!subscription,
  });

  const { data: svcData } = useQuery({
    queryKey: ['cost-by-svc', subscription, timeframe],
    queryFn:  () => fetchCostByService({ subscription_id: subscription, timeframe }),
    enabled:  !!subscription,
  });

  const { data: forecast } = useQuery({
    queryKey: ['forecast', subscription],
    queryFn:  () => fetchForecast({ subscription_id: subscription }),
    enabled:  !!subscription,
  });

  const { data: budgets } = useQuery({
    queryKey: ['budgets', subscription],
    queryFn:  () => fetchBudgets({ subscription_id: subscription }),
    enabled:  !!subscription,
  });

  const dailyRows = parseCostRows(costData?.data);
  const svcRows   = parseCostRows(svcData);
  const fcRows    = parseCostRows(forecast);

  // Build daily cost chart data
  const dailyChart = dailyRows
    .filter(r => r.UsageDate || r.BillingPeriodStartDate)
    .map(r => ({
      date: String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 10),
      cost: parseFloat(r.PreTaxCost || r.CostUSD || 0),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  // By service
  const svcChart = svcRows
    .map(r => ({ name: r.ServiceName || 'Other', cost: parseFloat(r.PreTaxCost || 0) }))
    .sort((a, b) => b.cost - a.cost)
    .slice(0, 12);

  const totalMonthly = dailyChart.reduce((s, r) => s + r.cost, 0);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Cost Explorer</div>
          <div className="page-sub">Live data from Microsoft.CostManagement API v2024-08-01</div>
        </div>
        <select value={timeframe} onChange={e => setTimeframe(e.target.value)}>
          <option value="MonthToDate">Month to Date</option>
          <option value="BillingMonthToDate">Billing Month to Date</option>
          <option value="TheLastMonth">Last Month</option>
        </select>
      </div>

      {!subscription && <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>Select a subscription to view cost data.</div>}

      {subscription && (
        <>
          <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
            <div className="stat-card accent">
              <div className="stat-label">MTD Spend</div>
              <div className="stat-value">${totalMonthly.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
              <div className="stat-sub">{timeframe}</div>
            </div>
            <div className="stat-card warning">
              <div className="stat-label">Budgets Active</div>
              <div className="stat-value">{(budgets || []).length}</div>
              <div className="stat-sub">Configured budgets</div>
            </div>
            <div className="stat-card purple">
              <div className="stat-label">Top Service</div>
              <div className="stat-value" style={{ fontSize: '1rem', marginTop: 4 }}>{svcChart[0]?.name || '—'}</div>
              <div className="stat-sub">${(svcChart[0]?.cost || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
            </div>
            <div className="stat-card success">
              <div className="stat-label">Services Tracked</div>
              <div className="stat-value">{svcChart.length}</div>
              <div className="stat-sub">Across this subscription</div>
            </div>
          </div>

          {/* Daily cost */}
          <div className="card" style={{ marginBottom: '1.25rem' }}>
            <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Daily Cost ({timeframe})</div>
            {loadCost ? <div className="empty-state"><div className="spin" /></div> : dailyChart.length === 0 ? <div className="empty-state"><p>No daily cost data available.</p></div> : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={dailyChart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                  <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} tickFormatter={v => `$${v.toLocaleString()}`} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }} formatter={v => [`$${parseFloat(v).toLocaleString()}`, 'Cost USD']} />
                  <Bar dataKey="cost" fill="#2563eb" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* By service */}
          <div className="card" style={{ marginBottom: '1.25rem' }}>
            <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Cost by Service (Top 12)</div>
            {svcChart.length === 0 ? <div className="empty-state"><p>No service data.</p></div> : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={svcChart} layout="vertical" margin={{ left: 120 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis type="number" tick={{ fill: 'var(--text3)', fontSize: 11 }} tickFormatter={v => `$${v.toLocaleString()}`} />
                  <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text2)', fontSize: 12 }} width={120} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }} formatter={v => [`$${parseFloat(v).toLocaleString()}`, 'Cost USD']} />
                  <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
                    {svcChart.map((e, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Budgets */}
          {(budgets || []).length > 0 && (
            <div className="card">
              <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '0.9rem' }}>Budgets</div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Name</th><th>Amount</th><th>Current Spend</th><th>Utilization</th></tr></thead>
                  <tbody>
                    {(budgets || []).map((b, i) => {
                      const p = b.properties || {};
                      const amt = p.amount || 0;
                      const cur = p.currentSpend?.amount || 0;
                      const pct = amt > 0 ? Math.round((cur / amt) * 100) : 0;
                      return (
                        <tr key={i}>
                          <td style={{ color: 'var(--text)', fontWeight: 500 }}>{b.name}</td>
                          <td>${amt.toLocaleString()}</td>
                          <td>${parseFloat(cur).toLocaleString()}</td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div className="progress-bar-bg" style={{ flex: 1 }}>
                                <div className="progress-bar-fill" style={{ width: `${Math.min(pct, 100)}%`, background: pct > 95 ? 'var(--danger)' : pct > 80 ? 'var(--warning)' : 'var(--success)' }} />
                              </div>
                              <span style={{ fontSize: '0.8rem', minWidth: 36 }}>{pct}%</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

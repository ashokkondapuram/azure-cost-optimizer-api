import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { fetchCosts } from '../api/client';

export default function Dashboard({ subscriptionId }) {
  const [timeframe, setTimeframe] = useState('MonthToDate');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    if (!subscriptionId) return setError('Enter a Subscription ID in the sidebar.');
    setLoading(true); setError('');
    try {
      const res = await fetchCosts(subscriptionId, timeframe);
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const rows = data?.data?.rows || [];
  const cols = data?.data?.columns || [];
  const dateIdx = cols.findIndex(c => c.name === 'UsageDate');
  const costIdx = cols.findIndex(c => c.name === 'PreTaxCost');
  const rgIdx = cols.findIndex(c => c.name === 'ResourceGroup');

  const chartData = rows.slice(0, 30).map(r => ({
    date: String(r[dateIdx] || ''),
    cost: parseFloat(r[costIdx] || 0),
    rg: r[rgIdx] || ''
  }));

  const totalCost = chartData.reduce((s, r) => s + r.cost, 0).toFixed(2);

  return (
    <div>
      <div className="stat-row">
        <div className="stat"><div className="label">Total Cost (filtered)</div><div className="value">${totalCost}</div></div>
        <div className="stat"><div className="label">Data Points</div><div className="value">{rows.length}</div></div>
      </div>
      <div className="card">
        <h2>Cost Overview</h2>
        <select value={timeframe} onChange={e => setTimeframe(e.target.value)}>
          <option value="MonthToDate">Month to Date</option>
          <option value="BillingMonthToDate">Billing Month to Date</option>
          <option value="TheLastMonth">Last Month</option>
          <option value="TheLastBillingMonth">Last Billing Month</option>
          <option value="WeekToDate">Week to Date</option>
        </select>
        <button onClick={load} style={{ marginTop: 8 }}>Fetch Costs</button>
        {loading && <p className="loading">Loading...</p>}
        {error && <p className="error">{error}</p>}
        {chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={300} style={{ marginTop: 20 }}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="cost" fill="#0078d4" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

import React, { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line, AreaChart, Area
} from 'recharts';
import { mockCosts } from '../api/mockData';

const COLORS = ['#0078d4','#00b4d8','#107c10','#d67f00','#8764b8','#e74c3c'];
const TIMEFRAMES = ['MonthToDate','BillingMonthToDate','TheLastMonth','TheLastBillingMonth','WeekToDate'];

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:'#fff', border:'1px solid #e1e5ef', borderRadius:8, padding:'10px 14px', boxShadow:'0 4px 16px rgba(0,0,0,0.1)' }}>
      <p style={{ fontWeight:600, marginBottom:4, fontSize:'0.8rem' }}>Day {label}</p>
      <p style={{ color:'#0078d4', fontWeight:600 }}>${payload[0].value}</p>
    </div>
  );
};

export default function Dashboard() {
  const [timeframe, setTimeframe] = useState('MonthToDate');
  const data = mockCosts.data;
  const cols = data.columns;
  const rows = data.rows;
  const costIdx = cols.findIndex(c => c.name === 'PreTaxCost');
  const dateIdx = cols.findIndex(c => c.name === 'UsageDate');
  const rgIdx   = cols.findIndex(c => c.name === 'ResourceGroup');

  const barData = rows.map(r => ({ date: String(r[dateIdx]).slice(6), cost: parseFloat(r[costIdx].toFixed(2)) }));

  const rgMap = {};
  rows.forEach(r => { const rg = r[rgIdx]; rgMap[rg] = (rgMap[rg]||0) + r[costIdx]; });
  const pieData = Object.entries(rgMap).map(([name,value]) => ({ name, value: parseFloat(value.toFixed(2)) }));

  const total     = rows.reduce((s,r) => s + r[costIdx], 0).toFixed(2);
  const avgDaily  = (parseFloat(total) / rows.length).toFixed(2);
  const maxDay    = Math.max(...rows.map(r => r[costIdx])).toFixed(2);

  const cumulativeData = barData.reduce((acc, item) => {
    const prev = acc.length ? acc[acc.length-1].cumulative : 0;
    acc.push({ ...item, cumulative: parseFloat((prev + item.cost).toFixed(2)) });
    return acc;
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>Cost Dashboard</h1>
        <p>Azure subscription spend analysis — {timeframe}</p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-icon">💰</span>
          <div className="stat-label">Total MTD Cost</div>
          <div className="stat-value blue">${total}</div>
          <div className="stat-sub">Across all resource groups</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📅</span>
          <div className="stat-label">Daily Average</div>
          <div className="stat-value">${avgDaily}</div>
          <div className="stat-sub">Per day this month</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📈</span>
          <div className="stat-label">Peak Day Spend</div>
          <div className="stat-value orange">${maxDay}</div>
          <div className="stat-sub">Highest single day</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">🗂</span>
          <div className="stat-label">Resource Groups</div>
          <div className="stat-value green">{pieData.length}</div>
          <div className="stat-sub">Billed this period</div>
        </div>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 380px', gap:20 }}>
        <div className="card">
          <div className="card-header">
            <h2>Daily Cost Trend</h2>
            <select value={timeframe} onChange={e => setTimeframe(e.target.value)} style={{ fontSize:'0.8rem' }}>
              {TIMEFRAMES.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={barData} margin={{ top:4, right:8, left:-10, bottom:4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="date" tick={{ fontSize:11 }} />
                <YAxis tick={{ fontSize:11 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="cost" fill="#0078d4" radius={[5,5,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h2>Cost by Resource Group</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="45%" innerRadius={55} outerRadius={90}>
                  {pieData.map((_,i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={v => `$${v}`} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize:'0.78rem' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h2>Cumulative Spend Trend</h2></div>
        <div className="card-body">
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={cumulativeData} margin={{ top:4, right:8, left:-10, bottom:4 }}>
              <defs>
                <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0078d4" stopOpacity={0.15}/>
                  <stop offset="95%" stopColor="#0078d4" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
              <XAxis dataKey="date" tick={{ fontSize:11 }} />
              <YAxis tick={{ fontSize:11 }} />
              <Tooltip formatter={v => `$${v}`} />
              <Area type="monotone" dataKey="cumulative" stroke="#0078d4" strokeWidth={2} fill="url(#blueGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

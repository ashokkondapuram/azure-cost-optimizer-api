import React, { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, AreaChart, Area
} from 'recharts';
import { mockSubscriptions, mockCostsBySubscription } from '../api/mockData';

const COLORS  = ['#0078d4','#107c10','#d67f00','#8764b8','#e74c3c','#00b4d8'];
const ENV_BADGE = { prod:'badge-red', staging:'badge-orange', dev:'badge-green' };
const ENV_COLOR = { prod:'#c0392b', staging:'#d67f00', dev:'#107c10' };

const CustomBar = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:'#fff', border:'1px solid #e1e5ef', borderRadius:8, padding:'10px 14px', boxShadow:'0 4px 16px rgba(0,0,0,0.1)' }}>
      <p style={{ fontWeight:600, fontSize:'0.78rem', color:'#9ba3b8', marginBottom:2 }}>Day {label}</p>
      <p style={{ color:'#0078d4', fontWeight:700, fontSize:'1rem' }}>${payload[0].value.toLocaleString()}</p>
    </div>
  );
};

export default function Dashboard() {
  const [activeSub, setActiveSub] = useState('sub-prod-001');
  const sub  = mockSubscriptions.find(s => s.id === activeSub);
  const data = mockCostsBySubscription[activeSub];
  const rows = data.rows;

  const barData = rows.map(r => ({ date: String(r[0]).slice(6), cost: r[1] }));
  const rgMap   = {};
  rows.forEach(r => { rgMap[r[2]] = (rgMap[r[2]]||0) + r[1]; });
  const pieData = Object.entries(rgMap).map(([name,value]) => ({ name, value: parseFloat(value.toFixed(0)) }));

  const cum = barData.reduce((acc, item) => {
    const prev = acc.length ? acc[acc.length-1].cumulative : 0;
    acc.push({ ...item, cumulative: parseFloat((prev+item.cost).toFixed(0)) });
    return acc;
  }, []);

  const avg  = (data.total / rows.length).toFixed(0);
  const peak = Math.max(...rows.map(r=>r[1])).toFixed(0);
  const budgetUsed = ((data.total / sub.budget)*100).toFixed(0);

  return (
    <div>
      <div className="page-header">
        <h1>Cost Dashboard</h1>
        <p>Real-time Azure subscription spend across all environments</p>
      </div>

      {/* Sub selector */}
      <div style={{ display:'flex', gap:10, marginBottom:24 }}>
        {mockSubscriptions.map(s => (
          <button key={s.id}
            onClick={() => setActiveSub(s.id)}
            className={`btn ${activeSub===s.id?'btn-primary':'btn-secondary'}`}
            style={{ gap:8 }}>
            <span style={{ width:8, height:8, borderRadius:'50%', background: activeSub===s.id?'#fff':ENV_COLOR[s.env], display:'inline-block' }} />
            {s.name}
          </button>
        ))}
      </div>

      {/* KPI row */}
      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-icon">💰</span>
          <div className="stat-label">Total MTD Cost</div>
          <div className="stat-value blue">${data.total.toLocaleString()}</div>
          <div className="stat-sub">Budget: ${sub.budget.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📊</span>
          <div className="stat-label">Budget Used</div>
          <div className={`stat-value ${budgetUsed>90?'red':budgetUsed>70?'orange':'green'}`}>{budgetUsed}%</div>
          <div style={{ marginTop:6 }}>
            <div style={{ background:'#f0f2f7', borderRadius:99, height:6 }}>
              <div style={{ width:`${Math.min(budgetUsed,100)}%`, background: budgetUsed>90?'#c0392b':budgetUsed>70?'#d67f00':'#107c10', height:'100%', borderRadius:99 }} />
            </div>
          </div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📅</span>
          <div className="stat-label">Daily Average</div>
          <div className="stat-value">${parseInt(avg).toLocaleString()}</div>
          <div className="stat-sub">Over {rows.length} days</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📈</span>
          <div className="stat-label">Peak Day</div>
          <div className="stat-value orange">${parseInt(peak).toLocaleString()}</div>
          <div className="stat-sub">Highest single day</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">🗂</span>
          <div className="stat-label">Resource Groups</div>
          <div className="stat-value">{pieData.length}</div>
          <div className="stat-sub">Billed groups</div>
        </div>
      </div>

      {/* All subscriptions overview */}
      <div className="card" style={{ marginBottom:20 }}>
        <div className="card-header"><h2>All Subscriptions Overview</h2></div>
        <div className="card-body">
          <table>
            <thead><tr><th>Subscription</th><th>Environment</th><th>MTD Spend</th><th>Budget</th><th>Utilization</th></tr></thead>
            <tbody>
              {mockSubscriptions.map(s => {
                const d = mockCostsBySubscription[s.id];
                const pct = Math.round((d.total/s.budget)*100);
                return (
                  <tr key={s.id} style={{ cursor:'pointer' }} onClick={() => setActiveSub(s.id)}>
                    <td><strong>{s.name}</strong> <span style={{ fontSize:'0.75rem', color:'#9ba3b8', fontFamily:'monospace' }}>{s.id}</span></td>
                    <td><span className={`badge badge-${s.env==='prod'?'blue':s.env==='staging'?'orange':'green'}`}>{s.env}</span></td>
                    <td><strong>${d.total.toLocaleString()}</strong></td>
                    <td>${s.budget.toLocaleString()}</td>
                    <td style={{ minWidth:180 }}>
                      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                        <div style={{ flex:1, background:'#f0f2f7', borderRadius:99, height:7 }}>
                          <div style={{ width:`${Math.min(pct,100)}%`, background:pct>90?'#c0392b':pct>70?'#d67f00':'#107c10', height:'100%', borderRadius:99 }} />
                        </div>
                        <span style={{ fontSize:'0.75rem', fontWeight:600, minWidth:32 }}>{pct}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Charts grid */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 360px', gap:20, marginBottom:20 }}>
        <div className="card">
          <div className="card-header"><h2>Daily Cost Trend — {sub.name}</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barData} margin={{ top:4, right:8, left:-10, bottom:4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="date" tick={{ fontSize:11 }} />
                <YAxis tick={{ fontSize:11 }} />
                <Tooltip content={<CustomBar />} />
                <Bar dataKey="cost" fill="#0078d4" radius={[5,5,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h2>Cost by Resource Group</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="45%" innerRadius={50} outerRadius={85}>
                  {pieData.map((_,i) => <Cell key={i} fill={COLORS[i%COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={v=>`$${v}`} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize:'0.75rem' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h2>Cumulative Spend — {sub.name}</h2></div>
        <div className="card-body">
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={cum} margin={{ top:4, right:8, left:-10, bottom:4 }}>
              <defs>
                <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0078d4" stopOpacity={0.15}/>
                  <stop offset="95%" stopColor="#0078d4" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
              <XAxis dataKey="date" tick={{ fontSize:11 }} />
              <YAxis tick={{ fontSize:11 }} />
              <Tooltip formatter={v=>`$${v}`} />
              <Area type="monotone" dataKey="cumulative" stroke="#0078d4" strokeWidth={2.5} fill="url(#blueGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

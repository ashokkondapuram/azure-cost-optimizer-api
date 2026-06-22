import React, { useState, useMemo } from 'react';
import { mockClusters, mockK8s } from '../api/mockData';
import UtilBar from '../components/UtilBar';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import StatusDot from '../components/StatusDot';

export default function K8sPage() {
  const [cluster, setCluster] = useState('aks-prod-primary');
  const [tab, setTab]         = useState('nodes');
  const [nsFilter, setNsFilter] = useState('all');

  const clusterNodes = useMemo(() => mockK8s.filter(r => r.cluster===cluster && !r.pod), [cluster]);
  const clusterPods  = useMemo(() => {
    const pods = mockK8s.filter(r => r.cluster===cluster && r.pod);
    return nsFilter==='all' ? pods : pods.filter(p=>p.namespace===nsFilter);
  }, [cluster, nsFilter]);

  const namespaces = [...new Set(mockK8s.filter(r=>r.cluster===cluster&&r.pod).map(r=>r.namespace))];

  const avgCpuPct = clusterNodes.length ? Math.round(clusterNodes.reduce((s,n)=>s+n.cpuPct,0)/clusterNodes.length) : 0;
  const avgMemPct = clusterNodes.length ? Math.round(clusterNodes.reduce((s,n)=>s+n.memPct,0)/clusterNodes.length) : 0;

  const cpuChart = clusterNodes.map(n => ({ node: n.node.split('-').slice(-1)[0], cpu: n.cpuPct }));
  const memChart = clusterNodes.map(n => ({ node: n.node.split('-').slice(-1)[0], mem: n.memPct }));

  const ENV_BADGE = { prod:'badge-blue', staging:'badge-orange', dev:'badge-green' };

  return (
    <div>
      <div className="page-header">
        <h1>Kubernetes Utilization</h1>
        <p>{mockClusters.length} clusters across {[...new Set(mockClusters.map(c=>c.sub))].length} subscriptions</p>
      </div>

      {/* Cluster selector cards */}
      <div style={{ display:'flex', gap:14, marginBottom:24 }}>
        {mockClusters.map(c => (
          <div key={c.name}
            onClick={() => { setCluster(c.name); setTab('nodes'); setNsFilter('all'); }}
            style={{
              flex:1, background:'#fff', borderRadius:12, padding:'16px 18px',
              border: cluster===c.name ? '2px solid #0078d4' : '1px solid #e1e5ef',
              cursor:'pointer', boxShadow: cluster===c.name ? '0 4px 16px rgba(0,120,212,0.15)' : '0 1px 3px rgba(0,0,0,0.06)',
              transition:'all 0.18s'
            }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:10 }}>
              <span style={{ fontWeight:700, fontSize:'0.9rem' }}>⎈ {c.name}</span>
              <span className={`badge ${ENV_BADGE[c.env]}`}>{c.env}</span>
            </div>
            <div style={{ fontSize:'0.78rem', color:'#5a6070', marginBottom:4 }}>📍 {c.location}</div>
            <div style={{ fontSize:'0.78rem', color:'#5a6070', marginBottom:8 }}>k8s {c.k8sVersion} &nbsp;·&nbsp; {c.nodeCount} nodes</div>
            <StatusDot status={c.status} />
          </div>
        ))}
      </div>

      {/* KPI */}
      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-icon">🖧</span>
          <div className="stat-label">Nodes</div>
          <div className="stat-value blue">{clusterNodes.length}</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📦</span>
          <div className="stat-label">Pods</div>
          <div className="stat-value">{mockK8s.filter(r=>r.cluster===cluster&&r.pod).length}</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">⚡</span>
          <div className="stat-label">Avg CPU</div>
          <div className={`stat-value ${avgCpuPct>80?'red':avgCpuPct>60?'orange':'green'}`}>{avgCpuPct}%</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">🧠</span>
          <div className="stat-label">Avg Memory</div>
          <div className={`stat-value ${avgMemPct>80?'red':avgMemPct>60?'orange':'green'}`}>{avgMemPct}%</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">🗂</span>
          <div className="stat-label">Namespaces</div>
          <div className="stat-value">{namespaces.length}</div>
        </div>
      </div>

      {/* Charts */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20, marginBottom:20 }}>
        <div className="card">
          <div className="card-header"><h2>CPU % per Node</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={cpuChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="node" tick={{ fontSize:10 }} />
                <YAxis domain={[0,100]} tick={{ fontSize:10 }} unit="%" />
                <Tooltip formatter={v=>`${v}%`} />
                <Bar dataKey="cpu" radius={[5,5,0,0]}
                  fill="#0078d4"
                  label={{ position:'top', fontSize:10, fill:'#5a6070', formatter:v=>`${v}%` }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h2>Memory % per Node</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={memChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="node" tick={{ fontSize:10 }} />
                <YAxis domain={[0,100]} tick={{ fontSize:10 }} unit="%" />
                <Tooltip formatter={v=>`${v}%`} />
                <Bar dataKey="mem" radius={[5,5,0,0]}
                  fill="#107c10"
                  label={{ position:'top', fontSize:10, fill:'#5a6070', formatter:v=>`${v}%` }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card">
        <div className="card-header">
          <h2>{tab==='nodes'?'Node Details':'Pod Details'}</h2>
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            {tab==='pods' && (
              <select value={nsFilter} onChange={e=>setNsFilter(e.target.value)} style={{ fontSize:'0.8rem' }}>
                <option value="all">All Namespaces</option>
                {namespaces.map(ns=><option key={ns}>{ns}</option>)}
              </select>
            )}
            <div className="tab-bar" style={{ marginBottom:0 }}>
              <button className={tab==='nodes'?'active':''} onClick={()=>setTab('nodes')}>🖧 Nodes</button>
              <button className={tab==='pods'? 'active':''} onClick={()=>setTab('pods')} >📦 Pods</button>
            </div>
          </div>
        </div>
        <div className="card-body">
          {tab==='nodes' ? (
            <table>
              <thead><tr><th>Node</th><th>CPU Usage</th><th style={{minWidth:180}}>CPU %</th><th>Memory Usage</th><th style={{minWidth:180}}>Memory %</th><th>Last Seen</th></tr></thead>
              <tbody>
                {clusterNodes.map((r,i)=>(
                  <tr key={i}>
                    <td><strong>{r.node}</strong></td>
                    <td><span className="badge badge-orange">{r.cpu}</span></td>
                    <td><UtilBar pct={r.cpuPct} color="#0078d4" /></td>
                    <td><span className="badge badge-green">{r.memory}</span></td>
                    <td><UtilBar pct={r.memPct} color="#107c10" /></td>
                    <td style={{ fontSize:'0.75rem', color:'#9ba3b8' }}>{r.recorded_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ):(
            <table>
              <thead><tr><th>Pod</th><th>Namespace</th><th>Node</th><th>CPU</th><th style={{minWidth:150}}>CPU %</th><th>Memory</th><th style={{minWidth:150}}>Mem %</th></tr></thead>
              <tbody>
                {clusterPods.map((r,i)=>(
                  <tr key={i}>
                    <td><strong>{r.pod}</strong></td>
                    <td><span className="badge badge-gray">{r.namespace}</span></td>
                    <td style={{ fontSize:'0.78rem', color:'#5a6070' }}>{r.node}</td>
                    <td><span className="badge badge-orange">{r.cpu}</span></td>
                    <td><UtilBar pct={r.cpuPct} color="#0078d4" /></td>
                    <td><span className="badge badge-green">{r.memory}</span></td>
                    <td><UtilBar pct={r.memPct} color="#107c10" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

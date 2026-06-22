import React, { useState } from 'react';
import { mockK8s } from '../api/mockData';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export default function K8sPage() {
  const [tab, setTab] = useState('nodes');
  const nodes = mockK8s.filter(r => !r.pod);
  const pods  = mockK8s.filter(r =>  r.pod);

  const cpuChart = nodes.map(n => ({
    node: n.node.split('-').slice(-1)[0],
    cpu:  parseInt(n.cpu),
  }));
  const memChart = nodes.map(n => ({
    node:   n.node.split('-').slice(-1)[0],
    memory: parseFloat(n.memory),
  }));

  return (
    <div>
      <div className="page-header">
        <h1>Kubernetes Utilization</h1>
        <p>AKS node and pod resource usage from metrics-server</p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-icon">🖧</span>
          <div className="stat-label">Nodes</div>
          <div className="stat-value blue">{nodes.length}</div>
          <div className="stat-sub">aks-prod-cluster</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📦</span>
          <div className="stat-label">Pods</div>
          <div className="stat-value">{pods.length}</div>
          <div className="stat-sub">Across all namespaces</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">⚡</span>
          <div className="stat-label">Avg CPU</div>
          <div className="stat-value orange">{Math.round(nodes.reduce((s,n)=>s+parseInt(n.cpu),0)/nodes.length)}m</div>
          <div className="stat-sub">Per node</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">🧠</span>
          <div className="stat-label">Avg Memory</div>
          <div className="stat-value green">{(nodes.reduce((s,n)=>s+parseFloat(n.memory),0)/nodes.length).toFixed(1)}Gi</div>
          <div className="stat-sub">Per node</div>
        </div>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20, marginBottom:20 }}>
        <div className="card">
          <div className="card-header"><h2>CPU Usage per Node (millicores)</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={cpuChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="node" tick={{ fontSize:11 }} />
                <YAxis tick={{ fontSize:11 }} />
                <Tooltip />
                <Bar dataKey="cpu" fill="#0078d4" radius={[5,5,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h2>Memory Usage per Node (Gi)</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={memChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="node" tick={{ fontSize:11 }} />
                <YAxis tick={{ fontSize:11 }} />
                <Tooltip />
                <Bar dataKey="memory" fill="#107c10" radius={[5,5,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{tab === 'nodes' ? 'Node Details' : 'Pod Details'}</h2>
          <div className="tab-bar" style={{ marginBottom:0 }}>
            <button className={tab==='nodes'?'active':''} onClick={() => setTab('nodes')}>🖧 Nodes</button>
            <button className={tab==='pods'? 'active':''} onClick={() => setTab('pods')} >📦 Pods</button>
          </div>
        </div>
        <div className="card-body">
          {tab === 'nodes' ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Cluster</th><th>Node</th><th>CPU Usage</th><th>Memory Usage</th><th>Recorded At</th></tr></thead>
                <tbody>
                  {nodes.map((r,i) => (
                    <tr key={i}>
                      <td><span className="badge badge-blue">{r.cluster}</span></td>
                      <td><strong>{r.node}</strong></td>
                      <td><span className="badge badge-orange">{r.cpu}</span></td>
                      <td><span className="badge badge-green">{r.memory}</span></td>
                      <td style={{ color:'#9ba3b8', fontSize:'0.78rem' }}>{r.recorded_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Namespace</th><th>Pod</th><th>CPU</th><th>Memory</th><th>Recorded At</th></tr></thead>
                <tbody>
                  {pods.map((r,i) => (
                    <tr key={i}>
                      <td><span className="badge badge-gray">{r.namespace}</span></td>
                      <td><strong>{r.pod}</strong></td>
                      <td><span className="badge badge-orange">{r.cpu}</span></td>
                      <td><span className="badge badge-green">{r.memory}</span></td>
                      <td style={{ color:'#9ba3b8', fontSize:'0.78rem' }}>{r.recorded_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

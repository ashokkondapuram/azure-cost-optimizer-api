import React, { useState, useMemo } from 'react';
import { mockClusters, mockK8s } from '../api/mockData';
import UtilBar   from '../components/UtilBar';
import StatusDot from '../components/StatusDot';
import EnvBadge  from '../components/EnvBadge';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, RadialBarChart, RadialBar } from 'recharts';

export default function K8sPage() {
  const [cluster,  setCluster]  = useState('aks-prod-primary');
  const [tab,      setTab]      = useState('nodes');
  const [nsFilter, setNsFilter] = useState('all');

  const clusterInfo  = mockClusters.find(c=>c.name===cluster);
  const clusterNodes = useMemo(()=>mockK8s.filter(r=>r.cluster===cluster&&!r.pod),[cluster]);
  const allPods      = useMemo(()=>mockK8s.filter(r=>r.cluster===cluster&&r.pod),[cluster]);
  const clusterPods  = useMemo(()=>nsFilter==='all'?allPods:allPods.filter(p=>p.namespace===nsFilter),[allPods,nsFilter]);
  const namespaces   = [...new Set(allPods.map(r=>r.namespace))];

  const avgCpu = clusterNodes.length?Math.round(clusterNodes.reduce((s,n)=>s+n.cpuPct,0)/clusterNodes.length):0;
  const avgMem = clusterNodes.length?Math.round(clusterNodes.reduce((s,n)=>s+n.memPct,0)/clusterNodes.length):0;

  const cpuChart = clusterNodes.map(n=>({ node:n.node.split('-').slice(-1)[0], cpu:n.cpuPct }));
  const memChart = clusterNodes.map(n=>({ node:n.node.split('-').slice(-1)[0], mem:n.memPct }));
  const radial   = [
    { name:'CPU', value:avgCpu, fill:avgCpu>80?'#c0392b':avgCpu>60?'#d67f00':'#0078d4' },
    { name:'Mem', value:avgMem, fill:avgMem>80?'#c0392b':avgMem>60?'#d67f00':'#107c10' },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>Kubernetes Clusters</h1>
        <p>{mockClusters.length} clusters · {mockK8s.filter(r=>!r.pod).length} total nodes · {mockK8s.filter(r=>r.pod).length} total pods</p>
      </div>

      {/* Cluster selector cards */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:14,marginBottom:24}}>
        {mockClusters.map(c=>(
          <div key={c.name}
            onClick={()=>{setCluster(c.name);setTab('nodes');setNsFilter('all');}}
            className={`cluster-card${cluster===c.name?' selected':''}`}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
              <div style={{display:'flex',alignItems:'center',gap:10}}>
                <div style={{width:38,height:38,borderRadius:9,background:'#326ce5',display:'flex',alignItems:'center',justifyContent:'center',fontSize:'1.3rem',flexShrink:0}}>⎈</div>
                <div>
                  <div style={{fontWeight:700,fontSize:'0.87rem',color:'#1a1d29'}}>{c.name}</div>
                  <div style={{fontSize:'0.72rem',color:'#9ba3b8',marginTop:1}}>{c.location}</div>
                </div>
              </div>
              <EnvBadge env={c.env} />
            </div>
            <div style={{display:'flex',gap:20,marginTop:14,paddingTop:12,borderTop:'1px solid #f0f2f7'}}>
              <div>
                <div style={{fontSize:'1.1rem',fontWeight:800,color:'#0078d4'}}>{c.nodeCount}</div>
                <div style={{fontSize:'0.66rem',color:'#9ba3b8',textTransform:'uppercase',letterSpacing:'0.05em'}}>Nodes</div>
              </div>
              <div>
                <div style={{fontSize:'0.85rem',fontWeight:700,color:'#1a1d29'}}>{c.k8sVersion}</div>
                <div style={{fontSize:'0.66rem',color:'#9ba3b8',textTransform:'uppercase',letterSpacing:'0.05em'}}>Version</div>
              </div>
              <div style={{marginLeft:'auto',display:'flex',alignItems:'flex-end'}}>
                <StatusDot status={c.status} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* KPI */}
      <div className="stat-row">
        {[{icon:'🖧',label:'Nodes',value:clusterNodes.length,cls:'blue',bg:'#e8f3fc'},
          {icon:'📦',label:'Pods', value:allPods.length,    cls:'',    bg:'#f3f0ff'},
          {icon:'⚡',label:'Avg CPU', value:`${avgCpu}%`, cls:avgCpu>80?'red':avgCpu>60?'orange':'green', bg:'#fff4ce'},
          {icon:'🧠',label:'Avg Mem', value:`${avgMem}%`, cls:avgMem>80?'red':avgMem>60?'orange':'green', bg:'#dff6dd'},
          {icon:'🗂',label:'Namespaces',value:namespaces.length,cls:'',bg:'#e8f3fc'},
        ].map((s,i)=>(
          <div className="stat-card" key={i}>
            <div className="stat-icon-wrap" style={{background:s.bg}}>{s.icon}</div>
            <div className="stat-label">{s.label}</div>
            <div className={`stat-value ${s.cls}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 200px',gap:16,marginBottom:16}}>
        <div className="card">
          <div className="card-header"><h2>CPU % per Node</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={170}>
              <BarChart data={cpuChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="node" tick={{fontSize:10}} />
                <YAxis domain={[0,100]} tick={{fontSize:10}} unit="%" />
                <Tooltip formatter={v=>`${v}%`} />
                <Bar dataKey="cpu" radius={[5,5,0,0]} fill="#0078d4"
                  label={{position:'top',fontSize:9,fill:'#5a6070',formatter:v=>`${v}%`}} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h2>Memory % per Node</h2></div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={170}>
              <BarChart data={memChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f2f7" />
                <XAxis dataKey="node" tick={{fontSize:10}} />
                <YAxis domain={[0,100]} tick={{fontSize:10}} unit="%" />
                <Tooltip formatter={v=>`${v}%`} />
                <Bar dataKey="mem" radius={[5,5,0,0]} fill="#107c10"
                  label={{position:'top',fontSize:9,fill:'#5a6070',formatter:v=>`${v}%`}} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h2>Health</h2></div>
          <div className="card-body" style={{display:'flex',flexDirection:'column',alignItems:'center',gap:8}}>
            <ResponsiveContainer width="100%" height={130}>
              <RadialBarChart cx="50%" cy="50%" innerRadius="35%" outerRadius="90%" data={radial}>
                <RadialBar dataKey="value" cornerRadius={6} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div style={{display:'flex',gap:10,fontSize:'0.72rem',fontWeight:700}}>
              <span style={{color:'#0078d4'}}>● CPU {avgCpu}%</span>
              <span style={{color:'#107c10'}}>● Mem {avgMem}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card">
        <div className="card-header">
          <h2>{tab==='nodes'?'Node Details':'Pod Details'}</h2>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            {tab==='pods'&&(
              <select value={nsFilter} onChange={e=>setNsFilter(e.target.value)} style={{fontSize:'0.8rem'}}>
                <option value="all">All Namespaces</option>
                {namespaces.map(ns=><option key={ns}>{ns}</option>)}
              </select>
            )}
            <div className="tab-bar" style={{marginBottom:0}}>
              <button className={tab==='nodes'?'active':''} onClick={()=>setTab('nodes')}>🖧 Nodes</button>
              <button className={tab==='pods'? 'active':''} onClick={()=>setTab('pods')} >📦 Pods</button>
            </div>
          </div>
        </div>
        <div className="card-body">
          {tab==='nodes'?(
            <div className="table-wrap">
              <table>
                <thead><tr><th>Node</th><th>CPU</th><th style={{minWidth:160}}>CPU %</th><th>Memory</th><th style={{minWidth:160}}>Mem %</th><th>Recorded</th></tr></thead>
                <tbody>
                  {clusterNodes.map((r,i)=>(
                    <tr key={i}>
                      <td><strong style={{fontFamily:'monospace',fontSize:'0.8rem'}}>{r.node}</strong></td>
                      <td><span className="badge badge-orange">{r.cpu}</span></td>
                      <td><UtilBar pct={r.cpuPct} color="#0078d4" /></td>
                      <td><span className="badge badge-green">{r.memory}</span></td>
                      <td><UtilBar pct={r.memPct} color="#107c10" /></td>
                      <td style={{fontSize:'0.72rem',color:'#9ba3b8'}}>{r.recorded_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ):(
            <div className="table-wrap">
              <table>
                <thead><tr><th>Pod</th><th>Namespace</th><th>Node</th><th>CPU</th><th style={{minWidth:140}}>CPU %</th><th>Memory</th><th style={{minWidth:140}}>Mem %</th></tr></thead>
                <tbody>
                  {clusterPods.map((r,i)=>(
                    <tr key={i}>
                      <td><strong style={{fontSize:'0.83rem'}}>{r.pod}</strong></td>
                      <td><span className="badge badge-gray">{r.namespace}</span></td>
                      <td style={{fontSize:'0.75rem',color:'#5a6070',fontFamily:'monospace'}}>{r.node}</td>
                      <td><span className="badge badge-orange">{r.cpu}</span></td>
                      <td><UtilBar pct={r.cpuPct} color="#0078d4" /></td>
                      <td><span className="badge badge-green">{r.memory}</span></td>
                      <td><UtilBar pct={r.memPct} color="#107c10" /></td>
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

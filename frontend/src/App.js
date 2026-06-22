import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import Dashboard   from './pages/Dashboard';
import Resources   from './pages/Resources';
import K8sPage     from './pages/K8sPage';
import CostHistory from './pages/CostHistory';

const PAGE_TITLES = {
  '/':         { title: 'Cost Dashboard',       sub: 'Azure Cost Management overview' },
  '/resources':{ title: 'Resource Inventory',   sub: 'All Azure resources across your subscription' },
  '/k8s':      { title: 'Kubernetes Utilization',sub: 'Node and pod metrics from AKS' },
  '/history':  { title: 'Cost Query History',   sub: 'Previously fetched cost records' },
};

function Topbar({ sub }) {
  const { pathname } = useLocation();
  const info = PAGE_TITLES[pathname] || PAGE_TITLES['/'];
  return (
    <div className="topbar">
      <div className="topbar-title">{info.title}<span style={{ fontWeight:400, color:'#9ba3b8', fontSize:'0.8rem', marginLeft:10 }}>{info.sub}</span></div>
      <div className="topbar-right">
        {sub && <span className="topbar-badge">🔗 {sub.slice(0,8)}…</span>}
        <span className="topbar-badge" style={{ background:'#dff6dd', color:'#107c10' }}>● Live</span>
      </div>
    </div>
  );
}

export default function App() {
  const [sub, setSub] = useState(localStorage.getItem('subscriptionId') || '');
  const handleSub = e => { setSub(e.target.value); localStorage.setItem('subscriptionId', e.target.value); };

  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <div className="sidebar-logo">
            <div className="logo-icon">☁️</div>
            <h1>Azure Cost Optimizer</h1>
            <p>FinOps Platform v2.0</p>
          </div>
          <div className="sidebar-sub">
            <label>Subscription ID</label>
            <input placeholder="Paste subscription ID…" value={sub} onChange={handleSub} />
          </div>
          <div className="sidebar-nav">
            <NavLink to="/" end><span className="nav-icon">📊</span> Dashboard</NavLink>
            <NavLink to="/resources"><span className="nav-icon">🗂</span> Resources</NavLink>
            <NavLink to="/k8s"><span className="nav-icon">⎈</span> Kubernetes</NavLink>
            <NavLink to="/history"><span className="nav-icon">📜</span> Cost History</NavLink>
          </div>
          <div className="sidebar-footer">Azure Cost Optimizer © 2026</div>
        </nav>
        <div className="main">
          <Topbar sub={sub} />
          <div className="page-content">
            <Routes>
              <Route path="/"          element={<Dashboard   sub={sub} />} />
              <Route path="/resources" element={<Resources   sub={sub} />} />
              <Route path="/k8s"       element={<K8sPage />} />
              <Route path="/history"   element={<CostHistory />} />
            </Routes>
          </div>
        </div>
      </div>
    </BrowserRouter>
  );
}

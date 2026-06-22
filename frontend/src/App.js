import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import Dashboard   from './pages/Dashboard';
import Resources   from './pages/Resources';
import K8sPage     from './pages/K8sPage';
import CostHistory from './pages/CostHistory';

const PAGES = {
  '/':          { title:'Cost Dashboard',        sub:'Subscription spend overview' },
  '/resources': { title:'Resource Inventory',    sub:'All Azure resources & optimization' },
  '/k8s':       { title:'Kubernetes Clusters',   sub:'AKS node & pod utilization' },
  '/history':   { title:'Cost Query History',    sub:'PostgreSQL audit log' },
};

function Topbar({ sub }) {
  const { pathname } = useLocation();
  const info = PAGES[pathname] || PAGES['/'];
  const now  = new Date().toLocaleString('en-CA', { dateStyle:'medium', timeStyle:'short' });
  return (
    <div className="topbar">
      <div className="topbar-left">
        <div className="topbar-title">{info.title}</div>
        <div className="topbar-sub">{info.sub}</div>
      </div>
      <div className="topbar-right">
        <span className="tb-chip chip-gray">🕐 {now}</span>
        {sub && <span className="tb-chip chip-blue">🔗 {sub.slice(0,8)}…</span>}
        <span className="tb-chip chip-green"><span className="pulse" />Live</span>
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
          <div className="sidebar-brand">
            <div className="brand-logo">
              <img src="https://upload.wikimedia.org/wikipedia/commons/f/fa/Microsoft_Azure.svg"
                alt="Azure" width={22} height={22} style={{ filter:'brightness(0) invert(1)' }} />
            </div>
            <div>
              <div className="brand-name">Azure Cost Optimizer</div>
              <div className="brand-ver">FinOps Platform · v2.0</div>
            </div>
          </div>

          <div className="sidebar-section-label">Subscription</div>
          <div className="sidebar-sub-input">
            <input placeholder="Paste subscription ID…" value={sub} onChange={handleSub} />
          </div>

          <div className="sidebar-section-label">Navigation</div>
          <div className="sidebar-nav">
            <NavLink to="/" end>
              <span className="nav-icon">📊</span><span>Dashboard</span>
            </NavLink>
            <NavLink to="/resources">
              <span className="nav-icon">🗂</span><span>Resources</span>
            </NavLink>
            <NavLink to="/k8s">
              <span className="nav-icon">⎈</span><span>Kubernetes</span>
            </NavLink>
            <NavLink to="/history">
              <span className="nav-icon">📜</span><span>Cost History</span>
            </NavLink>
          </div>

          <div className="sidebar-divider" />
          <div className="sidebar-footer">
            <div className="footer-user">
              <div className="avatar">AZ</div>
              <div>
                <div className="footer-name">FinOps Admin</div>
                <div className="footer-role">Cost Management</div>
              </div>
            </div>
          </div>
        </nav>

        <div className="main">
          <Topbar sub={sub} />
          <div className="page-content">
            <Routes>
              <Route path="/"          element={<Dashboard   sub={sub} />} />
              <Route path="/resources" element={<Resources />} />
              <Route path="/k8s"       element={<K8sPage />} />
              <Route path="/history"   element={<CostHistory />} />
            </Routes>
          </div>
        </div>
      </div>
    </BrowserRouter>
  );
}

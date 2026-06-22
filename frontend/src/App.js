import React, { createContext, useContext, useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Cpu, HardDrive, Network, Database,
  Shield, DollarSign, Settings, Search, Activity,
  ChevronDown, Bell, RefreshCw, Boxes, CloudCog
} from 'lucide-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fetchSubscriptions } from './api/azure';

import Dashboard     from './pages/Dashboard';
import CostExplorer  from './pages/CostExplorer';
import Findings      from './pages/Findings';
import VirtualMachines from './pages/VirtualMachines';
import AKSClusters   from './pages/AKSClusters';
import AllResources  from './pages/AllResources';
import EngineConfig  from './pages/EngineConfig';
import RunHistory    from './pages/RunHistory';

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1 } } });
export const AppCtx = createContext({});

function Shell() {
  const { subscription, setSubscription, subscriptions, loading } = useContext(AppCtx);
  const nav = useNavigate();

  const links = [
    { section: 'Overview' },
    { to: '/',           icon: <LayoutDashboard size={16} />, label: 'Dashboard' },
    { to: '/costs',      icon: <DollarSign size={16} />,     label: 'Cost Explorer' },
    { to: '/findings',   icon: <Activity size={16} />,       label: 'Findings' },
    { section: 'Resources' },
    { to: '/vms',        icon: <Cpu size={16} />,            label: 'Virtual Machines' },
    { to: '/aks',        icon: <Boxes size={16} />,          label: 'AKS Clusters' },
    { to: '/resources',  icon: <HardDrive size={16} />,      label: 'All Resources' },
    { section: 'Engine' },
    { to: '/engine',     icon: <CloudCog size={16} />,       label: 'Engine Config' },
    { to: '/history',    icon: <Search size={16} />,         label: 'Run History' },
  ];

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-logo">
          <CloudCog size={18} color="#2563eb" />
          Azure<span>FinOps</span>
        </div>

        {/* Subscription selector */}
        <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--border)' }}>
          <div className="topbar-label" style={{ marginBottom: 6 }}>Subscription</div>
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text3)', fontSize: '0.8rem' }}>
              <div className="spin" style={{ width: 14, height: 14 }} /> Loading...
            </div>
          ) : (
            <select
              value={subscription}
              onChange={e => setSubscription(e.target.value)}
              style={{ width: '100%', fontSize: '0.78rem', padding: '6px 8px' }}
            >
              <option value="">-- Select --</option>
              {subscriptions.map(s => (
                <option key={s.subscriptionId} value={s.subscriptionId}>
                  {s.displayName || s.subscriptionId}
                </option>
              ))}
            </select>
          )}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem 0' }}>
          {links.map((l, i) =>
            l.section ? (
              <div key={i} className="sidebar-section">{l.section}</div>
            ) : (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.to === '/'}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                {l.icon} {l.label}
              </NavLink>
            )
          )}
        </div>

        <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', fontSize: '0.72rem', color: 'var(--text3)' }}>
          v5.0 · AzureFinOps
        </div>
      </nav>

      {/* Main */}
      <main className="main-content">
        <Routes>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/costs"     element={<CostExplorer />} />
          <Route path="/findings"  element={<Findings />} />
          <Route path="/vms"       element={<VirtualMachines />} />
          <Route path="/aks"       element={<AKSClusters />} />
          <Route path="/resources" element={<AllResources />} />
          <Route path="/engine"    element={<EngineConfig />} />
          <Route path="/history"   element={<RunHistory />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [subscription, setSubscription] = useState('');
  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSubscriptions()
      .then(data => {
        const list = Array.isArray(data) ? data : (data?.value || []);
        setSubscriptions(list);
        if (list.length > 0 && !subscription) setSubscription(list[0].subscriptionId);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <QueryClientProvider client={qc}>
      <AppCtx.Provider value={{ subscription, setSubscription, subscriptions, loading }}>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
      </AppCtx.Provider>
    </QueryClientProvider>
  );
}
